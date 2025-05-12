# app/core/ai_batch_processor.py
import logging
import json
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import asyncio
import streamlit as st
from .ai_processor import AIProcessor

# Configure logging
logger = logging.getLogger(__name__)

class AIBatchProcessor:
    """Process content in batches through the AI processor"""
    
    def __init__(self):
        self.processor = AIProcessor()
        
    async def process_all_content(self, site_content: Dict[str, Any], 
                                document_content: Dict[str, Any],
                                mode: str = 'all',
                                progress_callback=None):
        """
        Process all content from websites and documents
        
        Args:
            site_content: Dictionary of website content
            document_content: Dictionary of document content
            mode: Processing mode ('all', 'batch', 'interactive')
            progress_callback: Optional callback for progress updates
        """
        # Combine both content sources into a unified format
        all_content = {}
        
        # Add website content
        if site_content:
            all_content.update(site_content)
            
        # Add document content
        if document_content:
            for doc_id, doc_data in document_content.items():
                # Skip duplicates (if any)
                if doc_id in all_content:
                    logger.warning(f"Duplicate content ID found: {doc_id}")
                    continue
                all_content[doc_id] = doc_data
        
        # Initialize results container in session state if not present
        if 'ai_processed_content' not in st.session_state:
            st.session_state.ai_processed_content = {}
        
        if mode == 'interactive':
            await self._process_interactive(all_content)
        elif mode == 'batch':
            await self._process_batch(all_content, progress_callback)
        else:  # mode == 'all'
            await self._process_all(all_content, progress_callback)
    
    async def _process_interactive(self, content_dict: Dict[str, Any]):
        """Process content one item at a time with interactive UI controls"""
        # Create a list of unprocessed items if not already in session state
        if 'unprocessed_items' not in st.session_state:
            st.session_state.unprocessed_items = list(content_dict.keys())
        
        # Check if we have any items left to process
        if not st.session_state.unprocessed_items:
            st.success("All items processed!")
            return
        
        # Get the next item to process
        content_id = st.session_state.unprocessed_items[0]
        content_data = content_dict[content_id]
        
        # Display content info
        content_container = st.empty()
        with content_container.container():
            st.write(f"### Processing: {content_id}")
            
            # Show preview of content
            st.write("**Content Preview:**")
            preview = content_data.get("content", "")[:300] + "..." if len(content_data.get("content", "")) > 300 else content_data.get("content", "")
            st.text_area("", preview, height=100)
            
            # Process/Skip buttons
            col1, col2 = st.columns(2)
            process = col1.button("Process this item", key=f"process_{content_id}")
            skip = col2.button("Skip", key=f"skip_{content_id}")
            
            if process:
                with st.spinner("Processing..."):
                    # Process the content
                    result = await self.processor.process_content(content_id, content_data)
                    
                    # Store the result
                    if result and result.get("processed", False):
                        st.session_state.ai_processed_content[content_id] = result
                        st.success("Processing complete!")
                        
                        # Show results preview
                        with st.expander("View results", expanded=True):
                            st.json(result)
                    else:
                        st.error(f"Processing failed: {result.get('error', 'Unknown error')}")
                
                # Remove from unprocessed items and continue
                st.session_state.unprocessed_items.pop(0)
                st.experimental_rerun()
                
            elif skip:
                # Skip this item
                st.info(f"Skipped {content_id}")
                st.session_state.unprocessed_items.pop(0)
                st.experimental_rerun()
                
            # Stop here until user action
            st.stop()
    
    async def _process_batch(self, content_dict: Dict[str, Any], progress_callback, batch_size=3):
        """Process content in small batches"""
        remaining_items = list(content_dict.keys())
        
        while remaining_items:
            # Get next batch
            batch = remaining_items[:batch_size]
            
            # Display batch info
            st.write(f"### Processing batch of {len(batch)} items")
            for item_id in batch:
                st.write(f"- {item_id}")
            
            if st.button("Process batch", key=f"batch_{len(remaining_items)}"):
                with st.spinner("Processing batch..."):
                    progress_bar = st.progress(0)
                    
                    for idx, item_id in enumerate(batch):
                        # Update progress
                        if progress_callback:
                            progress_callback(f"Processing {idx+1}/{len(batch)}: {item_id}", (idx+1)/len(batch))
                        
                        # Process item
                        result = await self.processor.process_content(item_id, content_dict[item_id])
                        
                        # Store result
                        if result and result.get("processed", False):
                            st.session_state.ai_processed_content[item_id] = result
                        
                        # Update progress bar
                        progress_bar.progress((idx+1)/len(batch))
                    
                    # Remove processed items
                    remaining_items = remaining_items[batch_size:]
                    
                    st.success(f"Batch processed successfully!")
            else:
                # Stop until user action
                st.stop()
    
    async def _process_all(self, content_dict: Dict[str, Any], progress_callback):
            """Process all content items at once with progress bar"""
            if not content_dict:
                st.warning("No content to process")
                return
                
            total_items = len(content_dict)
            
            # Process all items
            for idx, (content_id, content_data) in enumerate(content_dict.items(), 1):
                # Update progress
                progress = idx / total_items
                if progress_callback:
                    progress_callback(f"Processing {idx}/{total_items}: {content_id}", progress)
                
                # Process item
                result = await self.processor.process_content(content_id, content_data)
                
                # Store result
                if result and result.get("processed", False):
                    st.session_state.ai_processed_content[content_id] = result
            
            # Save all processed content
            if st.session_state.ai_processed_content:
                save_path = await self.processor.save_processed_content(st.session_state.ai_processed_content)
                st.success(f"All content processed and saved to {save_path}")
            else:
                st.warning("No content was successfully processed")