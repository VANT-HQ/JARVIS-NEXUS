# core/tools/browsing_tool.py
"""
JARVIS Intelligent Browsing Tool (Browserless)
==============================================

An optimized browserless automation tool designed for Local LLMs featuring:
1. quick_search   - Fast queries with filtered text compression for efficient context delivery.
2. deep_research  - Multi-step research and autonomous fact compilation with memory retention.
3. active_monitor - Resource-efficient tracking of specific webpage elements and selectors.
4. rpa_task       - Headless API form transitions (Deprecated native visual interactions).

Employs curl_cffi for advanced TLS fingerprint impersonation and Jina AI as an external proxy fallback.
"""

import os
import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Literal
from bs4 import BeautifulSoup

# Centralized Path Mapping and Configurations
from core.config import config

# Try to resolve external Jina AI permissions via Database configuration
try:
    JINA_AI_ENABLED = config.get("external_api")
except Exception:
    JINA_AI_ENABLED = False

# Safe handling of optional external packages
try:
    from curl_cffi import requests as cffi_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    print("⚠️ Warning: curl_cffi not installed. Install with: pip install curl_cffi")

try:
    from ddgs import DDGS  
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    print("⚠️ Warning: ddgs not installed. Install with: pip install ddgs")

# Prevent context window overflow inside local inference engines
MAX_LLM_TEXT_LENGTH = 3000  


class BrowserMode(str, Enum):
    """Operation modes for the Browsing Subsystem."""
    QUICK_SEARCH = "quick_search"
    DEEP_RESEARCH = "deep_research"
    ACTIVE_MONITOR = "active_monitor"
    RPA_TASK = "rpa_task"


class BrowsingTool:
    """
    Intelligent browserless client that scrapes and minifies web data 
    into concise context-friendly payloads for low-parameter local models.
    """
    
    def __init__(self, memory_manager=None):
        if not CURL_CFFI_AVAILABLE:
            raise ImportError("curl_cffi is required for headless operations. Run: pip install curl_cffi")
        
        self.memory = memory_manager
        self.monitoring_tasks = {}  # Store configs mapping task_id -> task_config
        print("🌐 Browsing Tool (Browserless Architecture) initialized successfully.")

    def _collapse_whitespace(self, text: str) -> str:
        """Compresses multiple continuous whitespaces and layout breaks into a single line to preserve tokens."""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    def _clean_and_format_for_llm(self, html_text: str, url: str) -> str:
        """
        Strips unnecessary layout structures (scripts, CSS style definitions, nav elements) 
        and crops raw markdown/text to safely fit within the target model's limits.
        """
        if not html_text:
            return ""
            
        try:
            # If content comes pre-parsed from Jina AI Reader, it is markdown; skip HTML text parser
            if html_text.startswith("Title:") or "Markdown" in html_text[:100]:
                cleaned_text = html_text
            else:
                soup = BeautifulSoup(html_text, 'html.parser')
                
                # Decompose non-informational nodes
                for unwanted in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    unwanted.decompose()

                title_tag = soup.find('title')
                title = title_tag.get_text(strip=True) if title_tag else "No Title"

                # Extract main conversational element if structures exist
                main_element = soup.select_one('article, main, [role="main"], .content, #content')
                if main_element:
                    raw_text = main_element.get_text(separator=' ', strip=True)
                else:
                    raw_text = soup.get_text(separator=' ', strip=True)
                    
                cleaned_text = f"Title: {title}\n\n{raw_text}"

            # Standardize structural alignment
            compact_text = self._collapse_whitespace(cleaned_text)
            
            # Apply strict context limits
            if len(compact_text) > MAX_LLM_TEXT_LENGTH:
                compact_text = compact_text[:MAX_LLM_TEXT_LENGTH] + "\n...[Content Truncated]..."
                
            return f"Source: {url}\n{compact_text}"
            
        except Exception as e:
            print(f"⚠️ Text extraction error: {e}")
            logging.error(f"Text extraction error: {e}")
            return "Failed to extract readable text from source."

    def _smart_fetch(self, url: str) -> str:
        """
        Fetches webpage data via curl_cffi using browser fingerprint spoofing (Chrome 110).
        Automatically falls back to Jina AI proxy Reader API if local scraping is blocked by Cloudflare/WAF walls.
        """
        try:
            # Phase 1: Direct client-side TLS impersonation 
            response = cffi_requests.get(
                url, 
                impersonate="chrome110", 
                timeout=15,
                headers={"Accept-Language": "en-US,en;q=0.9,ar;q=0.8"}
            )
            
            if response.status_code in (200, 201, 202):
                return response.text
                
            print(f"⚠️ Initial fetch blocked or failed for {url} (Status: {response.status_code}).")
            logging.warning(f"Initial fetch blocked or failed for {url} (Status: {response.status_code}).")
            
        except Exception as e:
            print(f"⚠️ Fetch exception for {url}: {e}")
            logging.error(f"Fetch exception for {url}: {e}")

        # Phase 2: Dynamic Failover to Jina AI proxy if enabled in security profiles
        if JINA_AI_ENABLED:
            print(f"💡 Falling back to Jina AI proxy for {url}...")
            try:
                jina_url = f"https://r.jina.ai/{url}"
                response = cffi_requests.get(
                    jina_url,
                    impersonate="chrome110",
                    timeout=20
                )
                if response.status_code == 200:
                    return response.text
                print(f"⚠️ Jina AI proxy failed with status: {response.status_code}")
                logging.warning(f"Jina AI proxy failed with status: {response.status_code}")
            except Exception as e:
                print(f"❌ Jina AI fallback exception: {e}")
                logging.error(f"Jina AI fallback exception: {e}")
        else:
            print("🚫 Jina AI fallback proxy is disabled in system config. Skipping.")

        return ""

    # =================================================================
    # Mode 1: Quick Search
    # =================================================================
    def quick_search(self, query: str, max_results: int = 5, extract_text: bool = True) -> Dict:
        """
        Performs a rapid engine crawl and returns compressed structured information.
        """
        print(f"🔍 Quick Search Query: '{query}'")
        
        if not DDGS_AVAILABLE:
            return {'success': False, 'error': 'ddgs package is unavailable.'}

        try:
            results = []
            
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=max_results))
            
            if not search_results:
                 print("⚠️ [Warning] No indices returned from search engine.")
            else:
                 print(f"💡 Discovered {len(search_results)} URLs. Extracting contents...")

            for result in search_results:
                try:
                    title = result.get('title', '')
                    link = result.get('href', '')
                    snippet = result.get('body', '')
                    
                    if not link:
                        continue

                    result_data = {
                        'title': title,
                        'link': link,
                        'snippet': snippet
                    }
                    
                    if extract_text:
                        html_text = self._smart_fetch(link)
                        clean_text = self._clean_and_format_for_llm(html_text, link)
                        result_data['full_text'] = clean_text
                    
                    results.append(result_data)
                except Exception as e:
                    print(f"⚠️ [Parse Error] Failed to process search item: {e}")
                    logging.error(f"Failed to process search item: {e}")
                    continue
            
            return {
                'success': True,
                'query': query,
                'results': results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Quick search system failure: {e}")
            logging.error(f"Quick search system failure: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query
            }

    # =================================================================
    # Mode 2: Deep Research
    # =================================================================
    def deep_research(self, topic: str, max_sources: int = 3, save_to_memory: bool = True) -> Dict:
        """
        Aggregates multi-source web indexing with autonomous fact parsing, 
        and archives verified data to long-term database knowledge structures.
        """
        print(f"🔬 Deep Research Engine Active: '{topic}'")
        
        research_plan = {
            'topic': topic,
            'findings': [],
            'facts_learned': []
        }
        
        try:
            # Step 1: Initial query discovery
            print("  [Step 1/3] Gathering deep source directories...")
            search_results = self.quick_search(query=topic, max_results=max_sources, extract_text=True)
            
            if not search_results['success']:
                return search_results
                
            # Step 2: Content contextual mining and analysis
            print("  [Step 2/3] Parsing documents and mining raw facts...")
            all_facts = []
            
            for source in search_results['results']:
                if not source.get('full_text'):
                    continue
                    
                facts = self._extract_key_facts(source['full_text'], topic)
                all_facts.extend(facts)
                
                finding = {
                    'source_title': source['title'],
                    'link': source['link'],
                    'extracted_facts': facts
                }
                research_plan['findings'].append(finding)
                
            # Deduplicate compiled insights
            research_plan['facts_learned'] = list(set(all_facts))

            # Step 3: Archive facts into the cognitive vector/relational databases
            if save_to_memory and self.memory and research_plan['facts_learned']:
                print("  [Step 3/3] Committing compiled intelligence pool into Memory...")
                
                facts_combined = " | ".join(research_plan['facts_learned'])
                memory_content = (
                    f"Deep Research regarding '{topic}'. Extracted Facts: {facts_combined}. "
                    f"Sources: {[f['link'] for f in research_plan['findings']]}"
                )
                
                # Routes through the modern unified memory manager schema
                self.memory.save_to_memory(
                    content=memory_content,
                    category='fact',
                    tags=['deep_research', 'auto_learned', topic]
                )

            return {
                'success': True,
                'topic': topic,
                'sources_analyzed': len(research_plan['findings']),
                'total_facts_learned': len(research_plan['facts_learned']),
                'facts': research_plan['facts_learned'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Deep research system execution failure: {e}")
            logging.error(f"Deep research system execution failure: {e}")
            return {
                'success': False,
                'error': str(e),
                'topic': topic
            }

    # =================================================================
    # Mode 3: Active Monitor
    # =================================================================
    def setup_monitor(self, url: str, check_selector: str, check_interval_hours: int = 6, notify_on_change: bool = True, task_name: str = None) -> str:
        """Configures headless target element monitors and schedules data checking tasks."""
        task_id = f"monitor_{int(time.time())}"
        task_name = task_name or f"Monitor {url}"
        
        task_config = {
            'task_id': task_id,
            'task_name': task_name,
            'url': url,
            'check_selector': check_selector,
            'check_interval_hours': check_interval_hours,
            'notify_on_change': notify_on_change,
            'last_check': None,
            'last_value': None,
            'created_at': datetime.now().isoformat()
        }
        
        self.monitoring_tasks[task_id] = task_config
        
        if self.memory:
            self.memory.create_task(
                title=task_name,
                description=f"Monitor {url} every {check_interval_hours} hours",
                priority=2,
                tags=['browser_monitor', 'automated'],
                related_memory_id=None
            )
        
        print(f"✅ Active HTML monitor established: {task_id}")
        return task_id
    
    def run_monitor_check(self, task_id: str) -> Dict:
        """Executes a real-time scraping test against scheduled CSS/HTML selectors."""
        if task_id not in self.monitoring_tasks:
            return {'success': False, 'error': 'Target active tracking task ID not found.'}
        
        task = self.monitoring_tasks[task_id]
        print(f"🔍 Monitoring target node structure: {task['task_name']}")
        
        try:
            html_text = self._smart_fetch(task['url'])
            if not html_text:
                return {'success': False, 'error': 'Failed to scrape tracking webpage.', 'task_id': task_id}
                
            soup = BeautifulSoup(html_text, 'html.parser')
            element = soup.select_one(task['check_selector'])
            
            if not element:
                return {
                    'success': False,
                    'error': 'Specified DOM CSS Selector was not found on target page layout.',
                    'task_id': task_id
                }
            
            current_value = self._collapse_whitespace(element.get_text())
            changed = task['last_value'] and current_value != task['last_value']
            
            task['last_check'] = datetime.now().isoformat()
            task['last_value'] = current_value
            
            result = {
                'success': True,
                'task_id': task_id,
                'task_name': task['task_name'],
                'current_value': current_value,
                'changed': changed,
                'timestamp': datetime.now().isoformat()
            }
            
            if changed and self.memory:
                self.memory.store_memory(
                    content=f"Monitor detected change in {task['task_name']}: {current_value}",
                    title=f"Change detected: {task['task_name']}",
                    memory_type='episodic',
                    importance=8,
                    tags=['monitor', 'alert', 'change']
                )
            
            return result
            
        except Exception as e:
            print(f"❌ Monitor verification parsing failure: {e}")
            logging.error(f"Monitor verification parsing failure: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task_id
            }

    # =================================================================
    # Mode 4: RPA Task (Headless Form Transitions API Alternative)
    # =================================================================
    def execute_rpa_task(self, task_type: Literal["fill_form", "click_button", "download_file"], url: str, params: Dict) -> Dict:
        """
        Deprecated: Native visual browser orchestration blocks are no longer natively supported 
        due to lightweight memory container configurations.
        """
        print(f"🤖 RPA Task call blocked: {task_type} on {url}")
        return {
            'success': False,
            'error': 'Visual interactive browser tasks are disabled in standard Browserless execution.',
            'suggestion': 'Execute operations directly via raw targeted HTTP Form Actions or REST payloads.'
        }
    
    # -----------------------------------------------------------------
    # Information Extraction and Processing Utilities
    # -----------------------------------------------------------------
    def _extract_attribute(self, text: str, attribute: str) -> Optional[str]:
        """Helper to match structural pattern data inside raw extracted text blocks."""
        patterns = {
            'bundle_size': r'(\d+\.?\d*\s*(?:kb|mb|KB|MB))',
            'popularity': r'(\d+[,\d]*)\s*(?:downloads|stars|users)',
            'version': r'v?(\d+\.\d+\.?\d*)',
            'price': r'\$(\d+\.?\d*)'
        }
        
        if attribute.lower() in patterns:
            match = re.search(patterns[attribute.lower()], text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def _extract_key_facts(self, text: str, topic: str, max_facts: int = 5) -> List[str]:
        """Extracts text sentences matching conversational topic markers."""
        if not text or len(text.strip()) < 10:
            return []
            
        normalized_text = text.replace('\n', '.').replace('\r', '.')
        sentences = [s.strip() for s in normalized_text.split('.') if len(s.strip()) > 15]
        topic_words = [word.lower() for word in topic.split() if len(word) > 2]
        
        relevant_sentences = []
        for s in sentences:
            s_lower = s.lower()
            matches = sum(1 for word in topic_words if word in s_lower)
            
            if matches > 0 and len(s) < 300:
                clean_sentence = " ".join(s.split())
                if clean_sentence not in relevant_sentences:
                    relevant_sentences.append(clean_sentence)
        
        if not relevant_sentences and sentences:
            print(f"💡 Keyword indexing yielded zero explicit rows for '{topic}'. Using fallback summaries.")
            return sentences[:max_facts]
            
        return relevant_sentences[:max_facts]


# =====================================================================
# Core JARVIS Integration Routing Interface
# =====================================================================
class BrowsingToolAPI:
    """System-wide abstraction layer to process engine web browsing requests."""
    
    def __init__(self, memory_manager=None):
        self.tool = BrowsingTool(memory_manager)
    
    def execute(self, mode: BrowserMode, params: Dict) -> Dict:
        try:
            if mode == BrowserMode.QUICK_SEARCH:
                return self.tool.quick_search(**params)
            
            elif mode == BrowserMode.DEEP_RESEARCH:
                return self.tool.deep_research(**params)
            
            elif mode == BrowserMode.ACTIVE_MONITOR:
                action = params.pop('action', 'setup')
                if action == 'setup':
                    task_id = self.tool.setup_monitor(**params)
                    return {'success': True, 'task_id': task_id}
                elif action == 'check':
                    return self.tool.run_monitor_check(params['task_id'])
            
            elif mode == BrowserMode.RPA_TASK:
                return self.tool.execute_rpa_task(**params)
            
            else:
                return {
                    'success': False,
                    'error': f'Invalid operating browser mode: {mode}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'mode': mode
            }
