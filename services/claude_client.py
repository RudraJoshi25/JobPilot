import os
import json
import time
import asyncio
from typing import Optional, Dict, Any, List, Type, TypeVar
from anthropic import Anthropic, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

load_dotenv()

T = TypeVar('T', bound=BaseModel)


class ClaudeClient:
    # RATE LIMITER: Class-level shared state for all instances
    # Updated for 500k tokens/minute limit
    _semaphore: Optional[asyncio.Semaphore] = None
    _lock: Optional[asyncio.Lock] = None
    _last_call_time: float = 0.0
    _semaphore_initialized = False

    # COST TRACKER: Class-level shared state for session cost tracking
    _total_cost: float = 0.0
    _calls_by_model: Dict[str, int] = {}
    _cache_hits: int = 0
    _total_calls: int = 0

    @classmethod
    def _ensure_rate_limiter(cls):
        """Ensure rate limiter is initialized (call once)."""
        if not cls._semaphore_initialized:
            try:
                # Try to get current loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    cls._semaphore = asyncio.Semaphore(5)  # Max 5 concurrent calls (increased from 2)
                    cls._lock = asyncio.Lock()
                    cls._semaphore_initialized = True
            except RuntimeError:
                # No event loop yet, will initialize on first async call
                pass

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 4096,
        temperature: float = 1.0
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment or provided")

        self.client = Anthropic(api_key=self.api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Try to initialize rate limiter
        self._ensure_rate_limiter()

        # # Initialize cost tracker counters if needed
        # if not hasattr(self.__class__, '_calls_by_model') or self.__class__._calls_by_model is None:
        #     self.__class__._calls_by_model = {}

    async def _rate_limit_wait(self):
        """
        RATE LIMITER: Enforce minimum 2 second gap between API calls.
        Uses asyncio.Lock to ensure only one call proceeds at a time through this gate.
        Reduced from 3s to 2s for 500k tokens/minute limit.
        """
        # Initialize if not done yet
        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            now = time.time()
            gap = now - self.__class__._last_call_time

            if gap < 2.0:
                wait_time = 2.0 - gap
                print(f"  [RATE LIMIT] Waiting {wait_time:.1f}s before next API call...", flush=True)
                await asyncio.sleep(wait_time)

            self.__class__._last_call_time = time.time()

    def _handle_rate_limit_error(self, attempt: int):
        """
        RATE LIMITER: Exponential backoff for 429 errors (safety net).
        Updated for 500k tokens/minute limit:
        - Attempt 1: wait 10s
        - Attempt 2: wait 20s
        - Attempt 3: wait 40s
        """
        wait_times = [10, 20, 40]
        wait_time = wait_times[min(attempt, len(wait_times) - 1)]
        print(f"  [RATE LIMIT 429] Waiting {wait_time}s before retry (attempt {attempt + 1}/3)...", flush=True)
        time.sleep(wait_time)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None
    ) -> str:
        """
        Synchronous generate with rate limiting and 429 handling.
        For async contexts, this will block but enforce rate limits.
        """
        messages = [{"role": "user", "content": prompt}]

        params = {
            "model": model or self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature
        }

        if system:
            params["system"] = system

        if stop_sequences:
            params["stop_sequences"] = stop_sequences

        # Retry loop with exponential backoff for 429 errors
        for attempt in range(3):
            try:
                # Simple synchronous rate limiting (minimum 2s gap)
                now = time.time()
                gap = now - self.__class__._last_call_time
                if gap < 2.0:
                    time.sleep(2.0 - gap)
                self.__class__._last_call_time = time.time()

                response = self.client.messages.create(**params)

                # COST TRACKING: Track usage and cost
                # self._track_cost(response, params["model"])

                return response.content[0].text

            except RateLimitError as e:
                if attempt < 2:
                    self._handle_rate_limit_error(attempt)
                else:
                    raise Exception(f"Rate limit exceeded after 3 retries: {e}")

            except Exception as e:
                if attempt < 2:
                    wait_time = 2 ** attempt
                    print(f"  [ERROR] API call failed, retrying in {wait_time}s: {str(e)[:100]}", flush=True)
                    time.sleep(wait_time)
                else:
                    raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        system_instruction = "You must respond with valid JSON only. Do not include any text before or after the JSON."
        if system:
            system_instruction = f"{system}\n\n{system_instruction}"

        response_text = self.generate(
            prompt=prompt,
            system=system_instruction,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature
        )

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text[:500]}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,))
    )
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None
    ) -> T:
        json_schema = response_model.model_json_schema()

        system_instruction = f"""You must respond with valid JSON that matches this schema:
{json.dumps(json_schema, indent=2)}

Respond with valid JSON only. Do not include any text before or after the JSON."""

        if system:
            system_instruction = f"{system}\n\n{system_instruction}"

        json_response = self.generate_json(
            prompt=prompt,
            system=system_instruction,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature
        )

        try:
            return response_model.model_validate(json_response)
        except ValidationError as e:
            raise ValueError(f"Response does not match expected schema: {e}\nResponse: {json_response}")

    def test_connection(self) -> bool:
        try:
            response = self.generate(
                prompt="Respond with the word 'success' if you receive this message.",
                max_tokens=10
            )
            return "success" in response.lower()
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
