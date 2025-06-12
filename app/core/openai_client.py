# app/core/openai_client.py
import os
import logging
import time
import json
from typing import Dict, Any, List, Optional, Union
from dotenv import load_dotenv

# Import OpenAI with proper error handling
try:
    import openai
    from openai.error import OpenAIError, RateLimitError, Timeout as APITimeoutError
except ImportError as e:
    logging.error(f"Error importing OpenAI: {e}")
    raise ImportError("Please install openai==0.28.1: pip install openai==0.28.1")

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class AIClient:
    """Flexible OpenAI client with configurable models for openai<1.0.0"""
    
    def __init__(self):
        """Initialize the OpenAI client with API key from environment"""
        # Get API key
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        openai.api_key = self.api_key
        
        # Get proxy from environment if set
        self.proxy = os.getenv("OPENAI_PROXY")
        if self.proxy:
            openai.proxy = self.proxy
            logger.info(f"Using OpenAI proxy: {self.proxy}")
        
        # Get model configurations from environment or use defaults
        self.initial_model = os.getenv("OPENAI_INITIAL_MODEL", "gpt-3.5-turbo")
        self.final_model = os.getenv("OPENAI_FINAL_MODEL", "gpt-3.5-turbo")
        
        logger.info(f"AI Client initialized with: Initial model: {self.initial_model}, Final model: {self.final_model}")
        
        # Configure retry parameters
        self.max_retries = 3
        self.retry_delay = 2  # seconds
    
    def process_content(self, 
                        content: str, 
                        system_prompt: str, 
                        user_prompt: str, 
                        model: Optional[str] = None, 
                        temperature: float = 0.2) -> Dict[str, Any]:
        """
        Process content through the OpenAI API with retries and error handling
        
        Args:
            content: The text content to process
            system_prompt: The system message to use
            user_prompt: The user message template to use
            model: Optional model override, otherwise uses initial_model
            temperature: Temperature setting (0.0 to 1.0)
            
        Returns:
            Parsed JSON response or error information
        """
        selected_model = model or self.initial_model
        for attempt in range(self.max_retries):
            try:
                formatted_user_prompt = user_prompt.format(content=content)
                logger.info(f"Sending request to {selected_model} (attempt {attempt+1}/{self.max_retries})")
                response = openai.ChatCompletion.create(
                    model=selected_model,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": formatted_user_prompt}
                    ],
                    request_timeout=60,
                    **({"proxies": {"http": self.proxy, "https": self.proxy}} if self.proxy else {})
                )
                result_json = response["choices"][0]["message"]["content"]
                try:
                    parsed_result = json.loads(result_json)
                    logger.info(f"Successfully processed content with {selected_model}")
                    return parsed_result
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing JSON response: {e}")
                    logger.error(f"Received content: {result_json[:500]}...")
                    if attempt == self.max_retries - 1:
                        return {
                            "error": "Failed to parse JSON response",
                            "raw_response": result_json[:1000]
                        }
            except RateLimitError as e:
                logger.warning(f"Rate limit exceeded: {e}. Waiting before retry.")
                time.sleep(self.retry_delay * (2 ** attempt))
            except APITimeoutError as e:
                logger.warning(f"Request timed out: {e}. Waiting before retry.")
                time.sleep(self.retry_delay * (2 ** attempt))
            except OpenAIError as e:
                logger.error(f"API error: {e}")
                if attempt == self.max_retries - 1:
                    return {"error": f"API error after {self.max_retries} attempts: {str(e)}"}
                time.sleep(self.retry_delay)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt == self.max_retries - 1:
                    return {"error": f"Unexpected error: {str(e)}"}
                time.sleep(self.retry_delay)
        return {"error": f"Failed after {self.max_retries} attempts"}
    
    def process_full_content(self, 
                            combined_content: Dict[str, Any], 
                            system_prompt: str, 
                            user_prompt: str,
                            is_voice: bool = True,
                            temperature: float = 0.3) -> Dict[str, Any]:
        """
        Process the full combined content with the final model
        
        Args:
            combined_content: The combined content from all sources
            system_prompt: The system message to use
            user_prompt: The user message template to use
            is_voice: Whether to optimize for voice (True) or text (False)
            temperature: Temperature setting (0.0 to 1.0)
            
        Returns:
            Processed final document
        """
        content_json = json.dumps(combined_content, ensure_ascii=False)
        formatted_user_prompt = user_prompt.format(
            content=content_json,
            output_type="voice" if is_voice else "text"
        )
        try:
            logger.info(f"Processing full content with {self.final_model}")
            response = openai.ChatCompletion.create(
                model=self.final_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_user_prompt}
                ],
                request_timeout=120,
                **({"proxies": {"http": self.proxy, "https": self.proxy}} if self.proxy else {})
            )
            result_json = response["choices"][0]["message"]["content"]
            try:
                parsed_result = json.loads(result_json)
                logger.info(f"Successfully processed full content")
                return parsed_result
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON response: {e}")
                return {
                    "error": "Failed to parse final JSON response",
                    "raw_response": result_json[:1000]
                }
        except Exception as e:
            logger.error(f"Error processing full content: {e}")
            return {"error": f"Error processing full content: {str(e)}"}