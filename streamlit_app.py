# streamlit_app.py
import streamlit as st
import asyncio
import json
from datetime import datetime
from pathlib import Path
import logging
import io
import os
import tempfile
from typing import Dict, Any, List
from dotenv import load_dotenv
from app.core.scraper import WebsiteScraper
from app.core.document_parser import DocumentParser

# Helper functions
def extract_plain_text(combined_content: Dict[str, Any]) -> str:
    """Extract plain text from combined content for download"""
    if not combined_content:
        return ""
        
    text_parts = []
    
    # Add title and description
    text_parts.append(combined_content.get("title", "Knowledge Base").upper())
    text_parts.append("")
    text_parts.append(combined_content.get("description", ""))
    text_parts.append("\n" + "="*50 + "\n")
    
    # Add sections
    for section in combined_content.get("sections", []):
        section_heading = section.get("heading", "")
        text_parts.append(f"\n\n{section_heading.upper()}\n")
        text_parts.append("="*len(section_heading) + "\n")
        
        # Add subsections
        for subsection in section.get("subheadings", []):
            sub_heading = subsection.get("heading", "")
            content = subsection.get("content", "")
            
            text_parts.append(f"\n{sub_heading}\n")
            text_parts.append("-"*len(sub_heading) + "\n")
            text_parts.append(content + "\n")
    
    # Add system prompt
    text_parts.append("\n\n" + "="*50 + "\n")
    text_parts.append("SYSTEM PROMPT:\n")
    text_parts.append(combined_content.get("system_prompt", ""))
    
    return "\n".join(text_parts)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure page
st.set_page_config(page_title="Voice Agent Builder", layout="wide")

# Initialize session state
if 'discovered_urls' not in st.session_state:
   st.session_state.discovered_urls = None
if 'site_content' not in st.session_state:
   st.session_state.site_content = None
if 'document_content' not in st.session_state:
   st.session_state.document_content = {}
if 'combined_content' not in st.session_state:
   st.session_state.combined_content = {}
if 'ai_processed_content' not in st.session_state:
   st.session_state.ai_processed_content = {}
if 'scraper' not in st.session_state:
    st.session_state.scraper = WebsiteScraper()
if 'parser' not in st.session_state:
    st.session_state.parser = DocumentParser()

async def save_scraped_data(data, filename_prefix="scraped_content"):
    """Save scraped data to files with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create 'data' directory if it doesn't exist
    save_dir = Path("data")
    save_dir.mkdir(exist_ok=True)
    
    # Save data
    filename = save_dir / f"{filename_prefix}_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return filename

# Create main sections
st.title("Voice Agent Builder")

# URL Discovery and Scraping Section
st.subheader("Step 1: Website Scanning & Scraping")

# URL Input and Discovery
url = st.text_input("Enter Website URL")

# Add file upload option for previously scraped content
st.write("--- OR ---")
uploaded_file = st.file_uploader("Load previously scraped content", type=['json'], key="upload_scraped_content")

if uploaded_file is not None:
    try:
        # Load the JSON data
        uploaded_content = json.load(uploaded_file)

        # Store in session state for processing
        st.session_state.site_content = uploaded_content

        # Show stats about loaded content
        st.success(f"Loaded {len(uploaded_content)} pages from file")

        # Display preview
        st.subheader("Preview Loaded Content")
        for url, content in uploaded_content.items():
            st.write(f"📌 **URL:** {url}")
            st.write(f"**Title:** {content['metadata']['title']}")
        
    except Exception as e:
        st.error(f"Error loading file: {str(e)}")

# Create containers for dynamic updates
status_placeholder = st.empty()
progress_placeholder = st.empty()

def update_status(message):
    status_placeholder.write(message)

if st.button("Discover Pages"):
    with st.spinner("Initializing scan..."):
        st.session_state.discovered_urls = asyncio.run(
            st.session_state.scraper.discover_urls(url, status_callback=update_status)
        )
        
        # Final stats after completion
        total_found = len(st.session_state.discovered_urls)
        
        # Show stats in columns
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Pages Found", total_found)
        with col2:
            page_types = set(url_info['type'] for url_info in st.session_state.discovered_urls)
            st.metric("Different Page Types", len(page_types))
        with col3:
            st.metric("Target Domain", st.session_state.scraper.base_domain)
        
        st.success(f"Scan complete! Found {total_found} pages")

# Display discovered URLs with checkboxes
if st.session_state.discovered_urls:
    st.write("### Select Pages to Scrape")
    
    # Add select/deselect all buttons in columns
    col1, col2 = st.columns(2)
    if col1.button("Select All"):
        for url in st.session_state.discovered_urls:
            st.session_state[f"select_{url['url']}"] = True
    if col2.button("Deselect All"):
        for url in st.session_state.discovered_urls:
            st.session_state[f"select_{url['url']}"] = False

    # Group URLs by type
    urls_by_type = {}
    for url_info in st.session_state.discovered_urls:
        url_type = url_info['type']
        if url_type not in urls_by_type:
            urls_by_type[url_type] = []
        urls_by_type[url_type].append(url_info)

    # Display URLs grouped by type
    for url_type, urls in urls_by_type.items():
        st.write(f"#### {url_type.title()} Pages")
        for url_info in urls:
            key = f"select_{url_info['url']}"
            # Fix for the Streamlit warning by only setting default value if needed
            if key not in st.session_state:
                st.session_state[key] = True
            # Use the key without specifying a default value
            st.checkbox(
                f"{url_info['title'] or url_info['url']}",
                key=key
            )

    # Scrape selected URLs
    if st.button("Scrape Selected Pages"):
        selected_urls = [
            url_info['url'] for url_info in st.session_state.discovered_urls
            if st.session_state[f"select_{url_info['url']}"]
        ]
        
        if not selected_urls:
            st.warning("Please select at least one page to scrape")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_scraping_progress(message, progress):
                status_text.write(message)
                progress_bar.progress(progress)

            with st.spinner(f"Scraping {len(selected_urls)} pages..."):
                # Process URLs with progress updates
                st.session_state.site_content = asyncio.run(
                    st.session_state.scraper.scrape_pages(
                        selected_urls, 
                        progress_callback=update_scraping_progress
                    )
                )
                
                # Show success and stats
                st.success(f"Successfully scraped {len(st.session_state.site_content)} pages")
                
                # Save scraped content
                saved_file = asyncio.run(save_scraped_data(st.session_state.site_content))
                st.success(f"Saved to: {saved_file}")
                
                # Display content preview
                st.subheader("Preview Scraped Content")

                for index, (url, content) in enumerate(st.session_state.site_content.items()):
                    st.write(f"### {content['metadata']['title']}")
                    st.write(f"📌 **URL:** {url}")
                    st.text_area(
                        "🔍 Content Preview", 
                        content['content'][:500] + "..." if len(content['content']) > 500 else content['content'],
                        height=100,
                        key=f"preview_{index}"
                    )
                    st.write("---")
                
                # Download option for scraped content
                st.download_button(
                    "Download Scraped Content",
                    data=json.dumps(st.session_state.site_content, indent=2),
                    file_name="scraped_content.json",
                    mime="application/json"
                )

# Document Upload Section
st.subheader("Step 2: Document Upload")

# Document upload interface
document_types = ["PDF Files", "Word Documents", "Text Files", "HTML Files"]
upload_description = f"Upload any of these document types: {', '.join(document_types)}"

# Multi-file uploader (outside any expander)
uploaded_files = st.file_uploader(
    upload_description, 
    type=["pdf", "docx", "doc", "txt", "html", "htm", "md"],
    accept_multiple_files=True,
    key="upload_documents"
)

# Process uploaded files
if uploaded_files:
    if st.button("Process Uploaded Documents"):
        with st.spinner("Processing documents..."):
            # Prepare files for batch processing
            files_to_process = []
            for uploaded_file in uploaded_files:
                file_bytes = uploaded_file.read()
                files_to_process.append({
                    "filename": uploaded_file.name,
                    "content": file_bytes
                })
            
            # Batch process all documents
            document_results = st.session_state.parser.batch_process_documents(files_to_process)
            
            # Store in session state
            st.session_state.document_content = document_results
            
            # Save to disk
            saved_file = asyncio.run(save_scraped_data(document_results, "document_content"))
            st.success(f"Processed {len(document_results)} documents. Saved to: {saved_file}")
            
            # Display document preview - NOT in an expander
            st.subheader("Document Preview")
            
            # Use tabs instead of nested expanders
            if document_results:
                doc_tabs = st.tabs([f"{content['metadata']['title']}" for filename, content in document_results.items()])
                
                for idx, (filename, content) in enumerate(document_results.items()):
                    with doc_tabs[idx]:
                        st.write(f"**Filename:** {filename}")
                        st.write(f"**Format:** {content['metadata']['format']}")
                        if 'description' in content['metadata']:
                            st.write(f"**Description:** {content['metadata']['description']}")
                        st.text_area(
                            "Content Preview", 
                            content['content'][:1000] + "..." if len(content['content']) > 1000 else content['content'],
                            height=200,
                            key=f"doc_preview_{filename}"
                        )
            
            # Download option
            st.download_button(
                "Download Processed Documents",
                data=json.dumps(document_results, indent=2),
                file_name="document_content.json",
                mime="application/json"
            )

# Content Processing Section
st.subheader("Step 3: AI Processing")

# Check if we have any content to process
has_website_content = bool(st.session_state.site_content)
has_document_content = bool(st.session_state.document_content)

if has_website_content or has_document_content:
    # Initialize AI Batch Processor if not already in session state
    if 'ai_batch_processor' not in st.session_state:
        from app.core.ai_batch_processor import AIBatchProcessor
        st.session_state.ai_batch_processor = AIBatchProcessor()
    
    # Display content summary
    st.write("### Content Summary")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Website Pages", len(st.session_state.site_content) if has_website_content else 0)
    with col2:
        st.metric("Documents", len(st.session_state.document_content) if has_document_content else 0)
    
    # Processing mode selection
    processing_mode = st.radio(
        "Select Processing Mode",
        ["Process All", "Process in Batches", "Interactive Processing"],
        key="processing_mode"
    )
    
    # Map UI selection to processing mode
    mode_mapping = {
        "Process All": "all",
        "Process in Batches": "batch",
        "Interactive Processing": "interactive"
    }
    
    selected_mode = mode_mapping[processing_mode]
    
    # Check for OpenAI API key
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        st.warning("OpenAI API key not found. Please add your API key to the .env file.")
        st.code("OPENAI_API_KEY=your_key_here", language="text")
    else:
        # Display model information
        st.write("### AI Model Configuration")
        initial_model = os.getenv("OPENAI_INITIAL_MODEL", "gpt-4o-mini")
        final_model = os.getenv("OPENAI_FINAL_MODEL", "gpt-4-turbo")
        
        st.info(f"Using {initial_model} for initial processing and {final_model} for final document creation.")
        
        # Start processing button
        if st.button("Start AI Processing"):
            # Single set of progress components
            with st.container():
                progress_container = st.empty()
                status_container = st.empty()
                
                # Progress tracking function
                def update_progress(message, progress):
                    status_container.write(message)
                    progress_container.progress(progress)
            
                with st.spinner("Processing content..."):
                    # Process using the batch processor
                    asyncio.run(
                        st.session_state.ai_batch_processor.process_all_content(
                            st.session_state.site_content,
                            st.session_state.document_content,
                            mode=selected_mode,
                            progress_callback=update_progress
                        )
                    )
    
    # Display processed content if available
    if 'ai_processed_content' in st.session_state and st.session_state.ai_processed_content:
        st.subheader("Processed Content")
        
        # Statistics
        num_processed = len(st.session_state.ai_processed_content)
        num_successful = sum(1 for item in st.session_state.ai_processed_content.values() if item.get("processed", False))
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Processed", num_processed)
        with col2:
            st.metric("Successfully Processed", num_successful)
        
        # Download option
        st.download_button(
            "Download Processed Content",
            data=json.dumps(st.session_state.ai_processed_content, indent=2),
            file_name="ai_processed_content.json",
            mime="application/json"
        )
        
        # Display preview of processed items
        st.write("### Preview Processed Content")
        
        for content_id, content_data in st.session_state.ai_processed_content.items():
            if content_data.get("processed", False):
                with st.expander(f"{content_data.get('title', content_id)}"):
                    # Show content summary
                    st.write(f"**Source:** {content_id}")
                    st.write(f"**Source Type:** {content_data.get('source_type', 'Unknown')}")
                    
                    # Show sections
                    sections = content_data.get("sections", [])
                    if sections:
                        for section in sections:
                            st.write(f"#### {section.get('heading', 'Section')}")
                            st.write(section.get("content", "No content"))
                            st.write(f"**Content Type:** {section.get('content_type', 'Unknown')}")
                            st.write("---")
                    else:
                        st.write("No sections found")
            else:
                st.error(f"Processing failed for {content_id}: {content_data.get('error', 'Unknown error')}")
    
    # Content Combination section (Step 4)
    if 'ai_processed_content' in st.session_state and st.session_state.ai_processed_content:
        st.subheader("Step 4: Content Combination")
        
        # Initialize Content Combiner if not already in session state
        if 'content_combiner' not in st.session_state:
            from app.core.content_combiner import ContentCombiner
            st.session_state.content_combiner = ContentCombiner()
            
        # Initialize combined_content if not already in session state
        if 'combined_content' not in st.session_state:
            st.session_state.combined_content = None
            
        # Display statistics about content to combine
        num_processed = len(st.session_state.ai_processed_content)
        num_successful = sum(1 for item in st.session_state.ai_processed_content.values() if item.get("processed", False))
        
        st.write("### Content Ready for Combination")
        st.write(f"You have {num_successful} successfully processed items that will be combined into a single document.")
        
        # Agent type selection
        st.write("### Select Agent Type")
        agent_type = st.radio(
            "Optimize final document for:",
            ["Voice Agent", "Text Agent"],
            key="agent_type"
        )
        
        is_voice = agent_type == "Voice Agent"
        
        # Display explanation of the selected type
        if is_voice:
            st.info("""
            **Voice Agent Optimization:**
            - Spells out numbers, dates, and measurements
            - Uses clear, phonetic language
            - Avoids abbreviations and symbols
            - Structures content for natural speech flow
            - Includes pronunciation guidance when needed
            """)
        else:
            st.info("""
            **Text Agent Optimization:**
            - Uses standard text formatting with numbers and abbreviations
            - Structures content for visual scanning
            - Utilizes bullet points and formatted lists
            - Includes technical terminology as written
            - Optimized for reading rather than speaking
            """)
            
        # Combine button
        if st.button("Create Final Document"):
            with st.spinner(f"Creating {agent_type}..."):
                # Single set of progress components
                progress_container = st.empty()
                status_container = st.empty()
                
                status_container.write("Processing with AI - this may take a few minutes...")
                progress_container.progress(0.5)  # Show indeterminate progress
                
                # Combine content
                combined_result = asyncio.run(
                    st.session_state.content_combiner.combine_content(
                        st.session_state.ai_processed_content,
                        is_voice=is_voice
                    )
                )
                
                # Update progress
                progress_container.progress(1.0)
                
                if combined_result.get("processed", False):
                    st.session_state.combined_content = combined_result
                    
                    # Save JSON version to file
                    saved_json_file = asyncio.run(
                        st.session_state.content_combiner.save_combined_content(combined_result)
                    )
                    
                    # For voice agents, also save the Elevenlabs text format
                    if is_voice:
                        saved_text_file = asyncio.run(
                            st.session_state.content_combiner.save_elevenlabs_text_format(combined_result)
                        )
                        status_container.success(
                            f"Created final document and saved to: {saved_json_file}\n"
                            f"Elevenlabs optimized text format saved to: {saved_text_file}"
                        )
                    else:
                        status_container.success(f"Created final document and saved to: {saved_json_file}")
                else:
                    error = combined_result.get("error", "Unknown error")
                    status_container.error(f"Error creating final document: {error}")
        
        # Display combined content if available
        if st.session_state.combined_content and st.session_state.combined_content.get("processed", False):
            combined_content = st.session_state.combined_content
            
            st.subheader("Final Document")
            
            # Show basic info
            st.write(f"### {combined_content.get('title', 'Knowledge Base')}")
            st.write(f"**Description:** {combined_content.get('description', '')}")
            
            # Add explanation for download options
            if is_voice:
                st.write("### Download Options")
                st.markdown("""
                **Choose from three format options:**
                
                1. **Complete JSON Document** - Contains all content and system prompt in structured format
                
                2. **Elevenlabs JSON Format** - Optimized for Elevenlabs voice agents with:
                   - Enhanced section boundaries for better RAG chunking
                   - Clearly formatted headings and subheadings
                   - Explicit visual section dividers
                
                3. **Elevenlabs TXT Format (Recommended)** - Plain text format with:
                   - Maximum compatibility with Elevenlabs upload
                   - Clear visual formatting that survives text processing
                   - Explicit section headings with boundary markers
                   - Optimized for RAG chunking algorithms
                
                The TXT format is recommended for best results with Elevenlabs voice agents
                as it ensures clear section boundaries are maintained during processing.
                """)
            else:
                st.write("### Download Options")
                st.markdown("""
                **Choose from two format options:**
                
                1. **Complete JSON Document** - Contains all content and system prompt in structured format
                
                2. **Plain Text Version** - Simplified text format with:
                   - Clean formatting for easy reading
                   - Section headings and dividers
                   - System prompt included at the end
                """)
            
            # Download options in columns
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Standard JSON download
                st.download_button(
                    "Download Complete Document (JSON)",
                    data=json.dumps(combined_content, indent=2),
                    file_name=f"agent_knowledge_base_{combined_content.get('agent_type', 'unknown')}.json",
                    mime="application/json"
                )
            
            # For voice agents, offer special Elevenlabs formats
            if combined_content.get("agent_type") == "voice":
                with col2:
                    # Elevenlabs JSON format
                    elevenlabs_format = st.session_state.content_combiner.get_elevenlabs_format(combined_content)
                    st.download_button(
                        "Download Elevenlabs Format (JSON)",
                        data=json.dumps(elevenlabs_format, indent=2),
                        file_name="elevenlabs_knowledge_base.json",
                        mime="application/json"
                    )
                
                with col3:
                    # NEW: Elevenlabs TXT format for better RAG chunking
                    elevenlabs_text = st.session_state.content_combiner.get_elevenlabs_text_format(combined_content)
                    st.download_button(
                        "Download Elevenlabs Format (TXT)",
                        data=elevenlabs_text,
                        file_name="elevenlabs_knowledge_base.txt",
                        mime="text/plain"
                    )
            else:
                # For text agents, offer standard text format
                with col2:
                    st.download_button(
                        "Download Plain Text Version",
                        data=extract_plain_text(combined_content),
                        file_name="agent_knowledge_base.txt",
                        mime="text/plain"
                    )
            
            # Show document contents
            st.write("### Document Contents")
            
            # Display sections with tabs for sections
            sections = combined_content.get("sections", [])
            if sections:
                section_tabs = st.tabs([section.get("heading", f"Section {i+1}") for i, section in enumerate(sections)])
                
                for i, (section, tab) in enumerate(zip(sections, section_tabs)):
                    with tab:
                        subheadings = section.get("subheadings", [])
                        
                        for sub in subheadings:
                            st.write(f"#### {sub.get('heading', 'Subsection')}")
                            st.write(sub.get("content", ""))
                            st.write("---")
            
            # Show system prompt
            st.write("### System Prompt")
            system_prompt = combined_content.get("system_prompt", "")
            st.text_area("System Prompt for Agent", system_prompt, height=200)
    else:
        st.subheader("Step 4: Content Combination")
        st.info("Complete Step 3: AI Processing before combining content into a final document")
else:
    st.warning("Please scrape a website or upload documents before processing")