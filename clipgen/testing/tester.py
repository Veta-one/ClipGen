"""Unified API tester for Gemini and OpenAI providers."""

import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

import google.generativeai as genai
from google.generativeai import GenerationConfig
from openai import OpenAI

logger = logging.getLogger('ClipGen')


class TestStatus(Enum):
    NOT_TESTED = "not_tested"
    TESTING = "testing"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of an API test."""
    success: bool
    duration: float = 0.0
    error_message: str = ""


class APITester:
    """Unified tester for Gemini and OpenAI API keys and models."""

    def __init__(self, config: Dict[str, Any], task_lock: threading.Lock):
        """Initialize tester.

        Args:
            config: Application config dict
            task_lock: Lock for current_task_event synchronization
        """
        self.config = config
        self.task_lock = task_lock
        self.current_task_event: Optional[threading.Event] = None
        self.genai_lock = threading.Lock()

        # Status tracking
        self.gemini_key_statuses: Dict[int, str] = {}
        self.gemini_model_statuses: Dict[int, str] = {}
        self.openai_key_statuses: Dict[int, str] = {}
        self.openai_model_statuses: Dict[int, str] = {}

        # Test times
        self.gemini_model_times: Dict[int, float] = {}
        self.openai_model_times: Dict[int, float] = {}

    def _create_cancel_event(self) -> threading.Event:
        """Create and register a cancel event."""
        cancel_event = threading.Event()
        with self.task_lock:
            self.current_task_event = cancel_event
        return cancel_event

    def _clear_cancel_event(self) -> None:
        """Clear the current cancel event."""
        with self.task_lock:
            self.current_task_event = None

    def _update_timestamp(self, key_data: Dict) -> None:
        """Update usage timestamp for a key."""
        now = time.time()
        if "usage_timestamps" not in key_data:
            key_data["usage_timestamps"] = []
        key_data["usage_timestamps"].append(now)
        # Keep only last 24 hours
        key_data["usage_timestamps"] = [
            ts for ts in key_data["usage_timestamps"]
            if now - ts < 86400
        ]

    # === Gemini Key Test ===

    def test_gemini_key(
        self,
        index: int,
        on_complete: Optional[Callable[[], None]] = None
    ) -> TestResult:
        """Test a Gemini API key.

        Args:
            index: Index in config["api_keys"]
            on_complete: Callback when test finishes

        Returns:
            TestResult with success status
        """
        api_keys = self.config.get("api_keys", [])
        if not (0 <= index < len(api_keys)):
            self.gemini_key_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Invalid key index")

        key_data = api_keys[index]
        key_to_test = key_data.get("key", "").strip()

        if not key_to_test:
            self.gemini_key_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Empty key")

        if not key_to_test.isascii():
            self.gemini_key_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Invalid characters in key")

        # Get original key to restore later
        original_key = None
        for k in api_keys:
            if k.get("active"):
                original_key = k.get("key")
                break

        cancel_event = self._create_cancel_event()

        with self.genai_lock:
            try:
                if cancel_event.is_set():
                    raise ValueError("Cancelled")

                genai.configure(api_key=key_to_test)
                model = genai.GenerativeModel(self.config.get("active_model", "gemini-2.0-flash"))
                response = model.generate_content(
                    "Test",
                    generation_config=GenerationConfig(temperature=0.0),
                    request_options={'timeout': 60}
                )

                if response and response.text.strip():
                    self.gemini_key_statuses[index] = TestStatus.SUCCESS.value
                    self._update_timestamp(key_data)
                    return TestResult(True)
                else:
                    raise ValueError("Empty response")

            except Exception as e:
                self.gemini_key_statuses[index] = TestStatus.ERROR.value
                return TestResult(False, error_message=str(e))

            finally:
                self._clear_cancel_event()
                # Restore original key
                if original_key and original_key != "YOUR_API_KEY_HERE":
                    genai.configure(api_key=original_key)
                if on_complete:
                    on_complete()

    # === Gemini Model Test ===

    def test_gemini_model(
        self,
        index: int,
        on_complete: Optional[Callable[[], None]] = None
    ) -> TestResult:
        """Test a Gemini model.

        Args:
            index: Index in config["gemini_models"]
            on_complete: Callback when test finishes

        Returns:
            TestResult with success status and duration
        """
        models = self.config.get("gemini_models", [])
        if not (0 <= index < len(models)):
            self.gemini_model_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Invalid model index")

        model_data = models[index]
        model_name = model_data.get("name", "").strip()

        if not model_name:
            self.gemini_model_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Empty model name")

        # Get active key
        active_key = None
        for k in self.config.get("api_keys", []):
            if k.get("active"):
                active_key = k.get("key")
                break

        if not active_key or active_key == "YOUR_API_KEY_HERE":
            self.gemini_model_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="No active API key")

        cancel_event = self._create_cancel_event()

        try:
            if cancel_event.is_set():
                raise ValueError("Cancelled")

            start_time = time.time()
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                "Test",
                generation_config=GenerationConfig(temperature=0.0),
                request_options={'timeout': 60}
            )

            if response and response.text.strip():
                duration = time.time() - start_time
                self.gemini_model_statuses[index] = TestStatus.SUCCESS.value
                self.gemini_model_times[index] = duration

                # Update config
                model_data["test_status"] = "success"
                model_data["test_duration"] = duration

                # Update key timestamp
                for k in self.config.get("api_keys", []):
                    if k.get("active"):
                        self._update_timestamp(k)
                        break

                return TestResult(True, duration=duration)
            else:
                raise ValueError("Empty response")

        except Exception as e:
            self.gemini_model_statuses[index] = TestStatus.ERROR.value
            self.gemini_model_times[index] = 0.0
            model_data["test_status"] = "error"
            model_data["test_duration"] = 0.0
            return TestResult(False, error_message=str(e))

        finally:
            self._clear_cancel_event()
            if on_complete:
                on_complete()

    # === OpenAI Key Test ===

    def test_openai_key(
        self,
        index: int,
        on_complete: Optional[Callable[[], None]] = None
    ) -> TestResult:
        """Test an OpenAI API key.

        Args:
            index: Index in config["openai_api_keys"]
            on_complete: Callback when test finishes

        Returns:
            TestResult with success status
        """
        api_keys = self.config.get("openai_api_keys", [])
        if not (0 <= index < len(api_keys)):
            self.openai_key_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Invalid key index")

        key_data = api_keys[index]
        api_key = key_data.get("key", "").strip()

        if not api_key:
            self.openai_key_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Empty key")

        base_url = self.config.get("openai_base_url")
        model = self.config.get("openai_active_model", "gpt-3.5-turbo")

        cancel_event = self._create_cancel_event()

        try:
            if cancel_event.is_set():
                raise ValueError("Cancelled")

            client = OpenAI(base_url=base_url, api_key=api_key)
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                timeout=10
            )

            self.openai_key_statuses[index] = TestStatus.SUCCESS.value
            self._update_timestamp(key_data)
            return TestResult(True)

        except Exception as e:
            err_msg = str(e)
            # Redact API key from error message
            if api_key and api_key in err_msg:
                err_msg = err_msg.replace(api_key, "***REDACTED***")
            self.openai_key_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message=err_msg)

        finally:
            self._clear_cancel_event()
            if on_complete:
                on_complete()

    # === OpenAI Model Test ===

    def test_openai_model(
        self,
        index: int,
        start_time: float,
        on_complete: Optional[Callable[[], None]] = None
    ) -> TestResult:
        """Test an OpenAI model.

        Args:
            index: Index in config["openai_models"]
            start_time: When test started (for duration calculation)
            on_complete: Callback when test finishes

        Returns:
            TestResult with success status and duration
        """
        models = self.config.get("openai_models", [])
        if not (0 <= index < len(models)):
            self.openai_model_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="Invalid model index")

        model_data = models[index]
        model_name = model_data.get("name", "").strip()

        # Get active key
        active_key = None
        for k in self.config.get("openai_api_keys", []):
            if k.get("active"):
                active_key = k.get("key")
                break

        if not active_key:
            self.openai_model_statuses[index] = TestStatus.ERROR.value
            return TestResult(False, error_message="No active API key")

        base_url = self.config.get("openai_base_url")

        try:
            client = OpenAI(base_url=base_url, api_key=active_key)
            client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                timeout=15
            )

            duration = time.time() - start_time
            self.openai_model_statuses[index] = TestStatus.SUCCESS.value
            self.openai_model_times[index] = duration

            model_data["test_status"] = "success"
            model_data["test_duration"] = duration

            return TestResult(True, duration=duration)

        except Exception as e:
            self.openai_model_statuses[index] = TestStatus.ERROR.value
            self.openai_model_times[index] = 0.0
            model_data["test_status"] = "error"
            model_data["test_duration"] = 0.0
            return TestResult(False, error_message=str(e))

        finally:
            if on_complete:
                on_complete()

    # === Status Getters ===

    def get_gemini_key_status(self, index: int) -> str:
        return self.gemini_key_statuses.get(index, TestStatus.NOT_TESTED.value)

    def get_gemini_model_status(self, index: int) -> str:
        return self.gemini_model_statuses.get(index, TestStatus.NOT_TESTED.value)

    def get_openai_key_status(self, index: int) -> str:
        return self.openai_key_statuses.get(index, TestStatus.NOT_TESTED.value)

    def get_openai_model_status(self, index: int) -> str:
        return self.openai_model_statuses.get(index, TestStatus.NOT_TESTED.value)

    def set_status(self, provider: str, item_type: str, index: int, status: str) -> None:
        """Set test status for an item.

        Args:
            provider: "gemini" or "openai"
            item_type: "key" or "model"
            index: Item index
            status: New status value
        """
        if provider == "gemini":
            if item_type == "key":
                self.gemini_key_statuses[index] = status
            else:
                self.gemini_model_statuses[index] = status
        else:
            if item_type == "key":
                self.openai_key_statuses[index] = status
            else:
                self.openai_model_statuses[index] = status
