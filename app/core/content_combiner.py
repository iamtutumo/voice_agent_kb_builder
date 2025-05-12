# app/core/content_combiner.py
import logging
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path
from .openai_client import AIClient

# Configure logging
logger = logging.getLogger(__name__)

class ContentCombiner:
    """Combine processed content and create final voice/text optimized document"""
    
    def __init__(self):
        """Initialize the content combiner with AI client and prompts"""
        self.ai_client = AIClient()
        
    def _get_system_prompt(self, is_voice: bool) -> str:
        """Get the system prompt for final document creation"""
        voice_specific = """
        For voice agent optimization:
        
        1. Format all text for optimal voice readability:
           - Spell out numbers, dates, and measurements for clarity (e.g., "twenty-five percent" not "25%")
           - Avoid abbreviations and replace with full words
           - Use phonetic clarity for complex terms
           - Include pronunciation guidance for technical terms
           - Structure content with clear verbal transitions
           
        2. Create a detailed system prompt in markdown format that includes these sections:
           # Personality
           - Define a friendly, proactive personality with specific traits
           - Include details on conversational style, tone, and approach
           - Describe how the agent should handle different user emotions
           
           # Environment
           - Define the context in which the agent operates
           - Specify the business domain and services
           - Clarify what the agent can help with
           
           # Tone
           - Use ellipses ("...") to indicate distinct, audible pauses
           - Direct the agent to pronounce special characters properly (e.g., say "dot" instead of ".")
           - Instruct to spell out acronyms and carefully pronounce complex terms
           - Recommend normalized, spoken language without abbreviations
           - Suggest incorporating brief affirmations, filler words, and occasional disfluencies
           - Include guidance for adapting to user's technical level
           
           # Goal
           - Define the primary purpose of the agent in detail
           - Specify how to handle different types of inquiries
           - Include guidance on providing solutions and next steps
           
           # Guardrails
           - Set clear boundaries on what the agent should/shouldn't do
           - Include instructions for handling challenging situations
           - Specify how to maintain a human-like, conversational quality
           - Provide direction on staying relevant and focused
           
        The system prompt should be extremely thorough and detailed, following the example of professional voice agent systems.
        """
        
        text_specific = """
        For text agent optimization:
        
        1. Format text for optimal reading clarity:
           - Structure content with appropriate formatting for visual scanning
           - Use bullet points and numbered lists where appropriate
           - Include relevant numbers, abbreviations, and technical terms as written
           - Organize content with clear headings and subheadings
           - Format for readability in text-based interfaces
           
        2. Create a detailed system prompt in markdown format that includes these sections:
           # Personality
           - Define a helpful, knowledgeable personality with specific traits
           - Include details on writing style, tone, and approach
           - Describe how the agent should respond to different user needs
           
           # Environment
           - Define the context in which the agent operates
           - Specify the business domain and services
           - Clarify what the agent can help with
           
           # Tone
           - Provide guidance on maintaining consistent writing style
           - Include instructions for adapting formality to match the user
           - Direct the agent on when to use formatting for emphasis
           - Recommend clear, concise writing approaches
           - Suggest incorporating conversational elements while staying professional
           - Include guidance for adapting to user's technical level
           
           # Goal
           - Define the primary purpose of the agent in detail
           - Specify how to handle different types of inquiries
           - Include guidance on providing solutions and next steps
           
           # Guardrails
           - Set clear boundaries on what the agent should/shouldn't do
           - Include instructions for handling challenging situations
           - Specify how to maintain a helpful, efficient quality
           - Provide direction on staying relevant and focused
           
        The system prompt should be extremely thorough and detailed, following the example of professional text-based agent systems.
        """
        
        # Base prompt for both types
        base_prompt = """You are an expert at creating comprehensive knowledge bases for AI assistants. Your task is to organize all the provided content into a single, coherent document that will serve as the knowledge base for a customer service agent.

Follow these important guidelines:
1. Combine similar information from different sources to eliminate redundancy
2. Organize content into logical categories and clear sections with descriptive headings
3. Structure the document for optimal RAG retrieval with clear section boundaries
4. Maintain factual accuracy - never add speculative or made-up information
5. Create both the knowledge base content AND an appropriate system prompt
6. Focus on creating clear section boundaries for effective RAG chunking
7. Be extremely thorough and comprehensive - include ALL relevant details
8. Preserve all specific information like prices, contacts, procedures, etc.

For the system prompt, follow this structure:
1. Use proper markdown format with # for main sections, ## for subsections
2. Create a detailed, comprehensive prompt (at least 400-500 words)
3. Include all five required sections (Personality, Environment, Tone, Goal, Guardrails)
4. Make the prompt specific to the business domain from the content
5. Include specific, actionable guidance the agent can follow
        """
        
        # Add the appropriate specific guidelines based on agent type
        if is_voice:
            return base_prompt + voice_specific
        else:
            return base_prompt + text_specific
    
    def _get_user_prompt(self) -> str:
        """Get the user prompt template for final document creation"""
        return """Please combine all the following content into a single, comprehensive knowledge base document for a {output_type} agent. This will be used for customer service purposes.

Processed Content:
{content}

Be extremely thorough and comprehensive - include ALL relevant information from the source content. Do not summarize or abbreviate important details. The agent will rely entirely on this knowledge base to assist users, so completeness is critical.

For each topic:
- Include all relevant facts, figures, policies, and procedures 
- Preserve all specific details such as pricing, dimensions, timelines, etc.
- Maintain all contact information, business hours, and service areas
- Include ALL relevant FAQs with complete answers
- Keep ALL troubleshooting steps and technical details intact

Return a JSON object with this EXACT structure:

```json
{{
  "title": "Knowledge Base Document Title",
  "description": "Comprehensive description of the knowledge base",
  "sections": [
    {{
      "heading": "Main section heading",
      "subheadings": [
        {{
          "heading": "Subsection heading",
          "content": "EXTREMELY thorough {output_type}-optimized content with ALL relevant details"
        }}
      ]
    }}
  ],
  "system_prompt": "Complete system prompt for the {output_type} agent formatted in markdown with # headings",
  "metadata": {{
    "source_count": 123,
    "primary_categories": ["category1", "category2"],
    "creation_date": "ISO date string"
  }}
}}
```

For the system prompt:
1. Use proper markdown format with # for main sections, ## for subsections
2. Include sections for: Personality, Environment, Tone, Goal, and Guardrails
3. Make it detailed and thorough - at least 15-20 lines long
4. Follow industry best practices for {output_type} agents
5. Include specific instructions for handling common customer service scenarios

Ensure the document structure has clear, logical organization for effective RAG chunking. All content must be {output_type}-optimized according to best practices. Document completeness is the highest priority - include EVERYTHING that could be useful to the agent.

Ensure your response is only the JSON object with no additional text."""
    
    async def combine_content(self, processed_content: Dict[str, Any], is_voice: bool) -> Dict[str, Any]:
        """Combine all processed content into a final document
        
        Args:
            processed_content: Dictionary of processed content
            is_voice: Whether to optimize for voice (True) or text (False)
            
        Returns:
            Combined and optimized document
        """
        # Extract only successfully processed content
        valid_content = {
            content_id: content_data for content_id, content_data in processed_content.items()
            if content_data.get("processed", False)
        }
        
        if not valid_content:
            logger.warning("No valid content to combine")
            return {
                "error": "No valid content to combine",
                "processed": False
            }
        
        try:
            logger.info(f"Combining content for {'voice' if is_voice else 'text'} agent")
            
            # Get appropriate prompts
            system_prompt = self._get_system_prompt(is_voice)
            user_prompt = self._get_user_prompt()
            
            # Process with final model
            result = self.ai_client.process_full_content(
                combined_content=valid_content,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                is_voice=is_voice
            )
            
            if "error" in result:
                logger.error(f"Error combining content: {result['error']}")
                return {
                    "error": result["error"],
                    "processed": False
                }
            
            # Add metadata
            result["processed"] = True
            result["agent_type"] = "voice" if is_voice else "text"
            result["processed_at"] = datetime.now().isoformat()
            result["source_count"] = len(valid_content)
            
            logger.info(f"Successfully combined content into final document")
            return result
                
        except Exception as e:
            logger.error(f"Error combining content: {e}")
            return {
                "error": str(e),
                "processed": False
            }
    
    async def save_combined_content(self, combined_content: Dict[str, Any]) -> Path:
        """Save combined content to a file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        agent_type = combined_content.get("agent_type", "unknown")
        
        # Create output directory
        save_dir = Path("data")
        save_dir.mkdir(exist_ok=True)
        
        # Save to file
        filename = save_dir / f"final_{agent_type}_agent_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(combined_content, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Saved combined content to {filename}")
        return filename
        
    def get_elevenlabs_format(self, combined_content: Dict[str, Any]) -> Dict[str, Any]:
        """Convert combined content to Elevenlabs compatible format
        
        This formats the content specifically for Elevenlabs voice agents with
        enhanced formatting for better RAG chunking.
        """
        if not combined_content.get("processed", False):
            return {"error": "Cannot convert unprocessed content"}
            
        # Extract content from the combined document
        title = combined_content.get("title", "Knowledge Base")
        sections = combined_content.get("sections", [])
        system_prompt = combined_content.get("system_prompt", "")
        
        # Create Elevenlabs document structure with system prompt
        elevenlabs_doc = {
            "title": title,
            "system_prompt": system_prompt,
            "knowledge_base": []
        }
        
        # Convert sections to Elevenlabs format with enhanced formatting for RAG
        for section_index, section in enumerate(sections, 1):
            main_heading = section.get("heading", "")
            subheadings = section.get("subheadings", [])
            
            # Format section heading with clear boundaries for RAG
            formatted_section_heading = f"SECTION {section_index}: {main_heading.upper()}"
            section_boundary = "=" * (len(formatted_section_heading) + 4)
            
            # Create a section header entry with clear boundaries
            elevenlabs_doc["knowledge_base"].append({
                "heading": formatted_section_heading,
                "content": f"{section_boundary}\n{formatted_section_heading}\n{section_boundary}"
            })
            
            # Add each subsection as a separate knowledge item with enhanced formatting
            for sub_index, sub in enumerate(subheadings, 1):
                sub_heading = sub.get("heading", "")
                content = sub.get("content", "")
                
                # Format subsection heading with clear boundaries
                formatted_sub_heading = f"TOPIC {section_index}.{sub_index}: {sub_heading}"
                sub_boundary = "-" * (len(formatted_sub_heading) + 4)
                
                # Combine heading and content with clear formatting for RAG chunking
                formatted_content = (
                    f"{sub_boundary}\n"
                    f"{formatted_sub_heading}\n"
                    f"{sub_boundary}\n\n"
                    f"{content}\n\n"
                )
                
                # Add enhanced entry to knowledge base
                elevenlabs_doc["knowledge_base"].append({
                    "heading": formatted_sub_heading,
                    "content": formatted_content
                })
            
            # Add section divider for clarity
            elevenlabs_doc["knowledge_base"].append({
                "heading": f"End of Section {section_index}",
                "content": f"\n{'*' * 50}\n\n"
            })
        
        return elevenlabs_doc
        
    def get_elevenlabs_text_format(self, combined_content: Dict[str, Any]) -> str:
        """
        Create a text file format for Elevenlabs that maximizes RAG chunking effectiveness.
        Returns a plain text string formatted for optimal chunking.
        """
        if not combined_content.get("processed", False):
            return "Error: Cannot create text format from unprocessed content"
            
        # Extract content from the combined document
        title = combined_content.get("title", "Knowledge Base")
        sections = combined_content.get("sections", [])
        
        # Create a list to store all text parts
        text_parts = []
        
        # Add title with distinctive formatting
        title_line = title.upper()
        title_boundary = "=" * len(title_line)
        text_parts.extend([
            title_boundary,
            title_line,
            title_boundary,
            "\n\n"
        ])
        
        # Add description if available
        description = combined_content.get("description", "")
        if description:
            text_parts.extend([
                "DESCRIPTION:",
                description,
                "\n" + "-" * 80 + "\n\n"
            ])
        
        # Process each section with enhanced formatting for RAG
        for section_index, section in enumerate(sections, 1):
            main_heading = section.get("heading", "")
            subheadings = section.get("subheadings", [])
            
            # Format section heading with clear boundaries for RAG
            formatted_section_heading = f"SECTION {section_index}: {main_heading.upper()}"
            section_boundary = "=" * len(formatted_section_heading)
            
            # Add section header with prominent boundaries
            text_parts.extend([
                section_boundary,
                formatted_section_heading,
                section_boundary,
                "\n\n"
            ])
            
            # Add each subsection with enhanced formatting
            for sub_index, sub in enumerate(subheadings, 1):
                sub_heading = sub.get("heading", "")
                content = sub.get("content", "")
                
                # Format subsection heading with clear boundaries
                formatted_sub_heading = f"TOPIC {section_index}.{sub_index}: {sub_heading}"
                sub_boundary = "-" * len(formatted_sub_heading)
                
                # Add subsection with formatted boundaries
                text_parts.extend([
                    sub_boundary,
                    formatted_sub_heading,
                    sub_boundary,
                    "\n\n",
                    content,
                    "\n\n"
                ])
            
            # Add section divider for clarity
            text_parts.append("\n" + "*" * 80 + "\n\n")
        
        # Join all parts with appropriate spacing
        return "\n".join(text_parts)
        
    async def save_elevenlabs_text_format(self, combined_content: Dict[str, Any]) -> Path:
        """Save content in the Elevenlabs-optimized text format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create output directory
        save_dir = Path("data")
        save_dir.mkdir(exist_ok=True)
        
        # Generate the text content
        text_content = self.get_elevenlabs_text_format(combined_content)
        
        # Save to file
        filename = save_dir / f"elevenlabs_knowledge_base_{timestamp}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text_content)
            
        logger.info(f"Saved Elevenlabs text format to {filename}")
        return filename