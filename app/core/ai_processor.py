# app/core/ai_processor.py
import os
import logging
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path
from .openai_client import AIClient

# Configure logging
logger = logging.getLogger(__name__)

class AIProcessor:
    """Process content with AI to extract and structure customer service information"""
    
    def __init__(self):
        """Initialize the processor with AI client and prompts"""
        self.ai_client = AIClient()
        
        # Load prompts
        self.system_prompt = self._get_system_prompt()
        self.user_prompt = self._get_user_prompt()
        
    def _get_system_prompt(self) -> str:
        """Get the system prompt for customer service information extraction"""
        return """You are an expert at organizing customer service information for AI assistants. Your task is to analyze content and extract information that would be relevant for customer service chatbots.

Follow these important guidelines:
1. Focus ONLY on information relevant to customer service (FAQs, services, contact details, policies, procedures, etc.)
2. Structure information clearly with proper sections and headings
3. Extract only text in a standard format - DO NOT create voice-optimized versions yet
4. Organize information in a logical structure with consistent formatting
5. Maintain factual accuracy - never add speculative or made-up information
6. Extract ONLY information that exists in the source content

Your output MUST be valid JSON that follows the specified schema EXACTLY."""
    
    def _get_user_prompt(self) -> str:
        """Get the user prompt template for processing individual content"""
        return """Please analyze the following content and extract all customer service relevant information.

Content to analyze:
{content}

Return a JSON object with this EXACT structure:

```json
{{
  "source_type": "website or document",
  "title": "Clear descriptive title",
  "sections": [
    {{
      "heading": "Section heading",
      "content": "Extracted information in standard text format",
      "content_type": "faq|service|contact|policy|pricing|hours|location"
    }}
  ],
  "metadata": {{
    "primary_topics": ["topic1", "topic2"],
    "suggested_questions": ["question1", "question2"]
  }}
}}
```

Include ONLY real information from the content. If certain information isn't available, use empty arrays or null values rather than making up information. Structure each section to be self-contained and logically organized.

Ensure your response is only the JSON object with no additional text."""
    
    async def process_content(self, content_id: str, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single piece of content to extract customer service information
        
        Args:
            content_id: Identifier for the content (URL or filename)
            content_data: Dictionary with content and metadata
            
        Returns:
            Processed content with extracted customer service information
        """
        # Get raw content
        raw_content = content_data.get("content", "")
        metadata = content_data.get("metadata", {})
        
        if not raw_content:
            logger.warning(f"Empty content for {content_id}")
            return {
                "content_id": content_id,
                "error": "Empty content",
                "processed": False
            }
        
        try:
            # Log processing start
            logger.info(f"Processing {content_id}")
            
            # Determine source type
            source_type = "document" if metadata.get("format") else "website"
            
            # Add metadata to content to provide context
            if metadata:
                context = f"Title: {metadata.get('title', 'Unknown')}\n"
                if source_type == "document":
                    context += f"Document format: {metadata.get('format', 'Unknown')}\n"
                else:
                    context += f"URL: {content_id}\n"
                
                content_with_context = f"{context}\n{raw_content}"
            else:
                content_with_context = raw_content
            
            # Process with AI
            result = self.ai_client.process_content(
                content=content_with_context,
                system_prompt=self.system_prompt,
                user_prompt=self.user_prompt
            )
            
            if "error" in result:
                logger.error(f"Error processing {content_id}: {result['error']}")
                return {
                    "content_id": content_id,
                    "error": result["error"],
                    "processed": False
                }
            
            # Add source identifier to the result
            result["content_id"] = content_id
            result["processed"] = True
            result["processed_at"] = datetime.now().isoformat()
            
            # Validate result structure
            if self._validate_result(result):
                logger.info(f"Successfully processed {content_id}")
                return result
            else:
                logger.error(f"Invalid result structure for {content_id}")
                return {
                    "content_id": content_id,
                    "error": "Invalid result structure",
                    "processed": False,
                    "raw_result": result
                }
                
        except Exception as e:
            logger.error(f"Error processing {content_id}: {e}")
            return {
                "content_id": content_id,
                "error": str(e),
                "processed": False
            }
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate the structure of the AI processing result"""
        # Check essential fields
        required_fields = ["title", "sections"]
        for field in required_fields:
            if field not in result:
                logger.error(f"Missing required field: {field}")
                return False
        
        # Check sections structure
        sections = result.get("sections", [])
        if not isinstance(sections, list):
            logger.error("Sections must be an array")
            return False
            
        # Validate each section
        for section in sections:
            if not isinstance(section, dict):
                logger.error("Section must be an object")
                return False
                
            # Check section structure
            section_fields = ["heading", "content"]
            missing_fields = [field for field in section_fields if field not in section]
            if missing_fields:
                logger.error(f"Section missing fields: {missing_fields}")
                return False
        
        return True
    
    async def process_all_content(self, content_dict: Dict[str, Dict[str, Any]], 
                                progress_callback=None) -> Dict[str, Dict[str, Any]]:
        """Process all content items and track progress
        
        Args:
            content_dict: Dictionary of content items {id: content_data}
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary of processed content items
        """
        processed_results = {}
        total_items = len(content_dict)
        
        for idx, (content_id, content_data) in enumerate(content_dict.items(), 1):
            # Process content
            result = await self.process_content(content_id, content_data)
            processed_results[content_id] = result
            
            # Update progress
            progress = idx / total_items
            if progress_callback:
                progress_callback(f"Processed {idx}/{total_items}: {content_id}", progress)
                
        return processed_results
    
    async def save_processed_content(self, processed_content: Dict[str, Any], filename_prefix: str = "processed_content") -> Path:
        """Save processed content to a file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create output directory
        save_dir = Path("data")
        save_dir.mkdir(exist_ok=True)
        
        # Save to file
        filename = save_dir / f"{filename_prefix}_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(processed_content, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Saved processed content to {filename}")
        return filename