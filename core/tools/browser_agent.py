# core/tools/browser_agent.py
"""
JARVIS Intelligent Browser Agent
==================================

Browser automation tool with multiple operation modes:
1. quick_search - Fast search returning results
2. deep_research - Multi-step research with comparisons
3. active_monitor - Periodic monitoring of web pages
4. auto_learn - Autonomous learning and memory storage
5. rpa_task - Execute automated tasks (form filling, clicks, etc.)

Uses Scrapling for advanced web scraping with anti-detection
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Literal
from enum import Enum
from bs4 import BeautifulSoup

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

# =================================================================
# Dynamic System Paths (Fully dependent on unified config)
# =================================================================
# 1. Add Project Root to Python path to read the core folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 2. Import custom browser path from the unified config file
try:
    from core.config import config, CAMOUFOX_BROWSER_PATH
except ImportError as e:
    CAMOUFOX_BROWSER_PATH = None
    print(f"   [BrowserAgent] ⚠️ Warning: Could not import config properly. {e}")

try:
    # Removed the bulky StealthyFetcher and kept only the lightweight Fetcher
    from scrapling import Fetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    print("⚠️ Scrapling not installed. Install with: pip install scrapling")

try:
    from ddgs import DDGS  
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    print("⚠️ ddgs not installed. Install with: pip install ddgs")

class BrowserMode(str, Enum):
    """Browser Agent operation modes"""
    QUICK_SEARCH = "quick_search"
    DEEP_RESEARCH = "deep_research"
    ACTIVE_MONITOR = "active_monitor"
    AUTO_LEARN = "auto_learn"
    RPA_TASK = "rpa_task"


class BrowserAgent:
    """
    Intelligent Browser Agent
    """
    
    def __init__(self, memory_manager=None):
        """
        Args:
            memory_manager: optional MemoryManager instance for storing findings
        """
        if not SCRAPLING_AVAILABLE:
            raise ImportError("Scrapling is required. Install: pip install scrapling")
        
        self.memory = memory_manager
        
        # Fetcher configurations
        self.fetcher = None  # Initialize when needed
        self.stealthy_fetcher = None  # For protected websites
        
        # Monitoring state
        self.monitoring_tasks = {}  # {task_id: task_config}
        
        print("🌐 Browser Agent initialized")
    
    def _get_fetcher(self):
        """
        Get a lightweight Fetcher only for standard requests
        """
        if not self.fetcher:
            Fetcher.configure()
            self.fetcher = Fetcher()
        return self.fetcher
        
    def _smart_fetch(self, url: str):
        """
        Smart function relying on a fast HTTP Client.
        If the site is protected, it directly opens the custom Camoufox browser and controls it.
        """
        fast_fetcher = self._get_fetcher()
        try:
            response = fast_fetcher.get(url)
            
            if response.status in [401, 403, 429, 503]:
                print(f"⚠️ Site protected {url} (Status: {response.status}). Falling back to Native Camoufox...")
                
                try:
                    # Directly use the core engine (Patchright) that Scrapling is built upon
                    from patchright.sync_api import sync_playwright
                except ImportError:
                    print("⚠️ Patchright not installed.")
                    return ""
                
                path_str = str(CAMOUFOX_BROWSER_PATH) if CAMOUFOX_BROWSER_PATH else None
                
                if not path_str or not os.path.exists(path_str):
                    print(f"⚠️ Camoufox executable not found at: {path_str}")
                    return ""
                
                try:
                    # Full and direct control over the built-in browser
                    with sync_playwright() as p:
                        browser = p.firefox.launch(executable_path=path_str, headless=True)
                        page = browser.new_page()
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        html_content = page.content()
                        browser.close()
                        return html_content
                except Exception as browser_error:
                    print(f"❌ Camoufox fallback failed: {browser_error}")
                    return ""
                
            return response.text if hasattr(response, 'text') else ""
            
        except Exception as e:
            print(f"⚠️ [Fetch Error] Failed to read {url}: {e}")
            return ""
    
    # =================================================================
    # Mode 1: Quick Search
    # =================================================================
    
    def quick_search(
        self, 
        query: str,
        max_results: int = 5,
        extract_text: bool = True
    ) -> Dict:
        """
        Quick search returning results using a direct API (100% stable, no blocks)
        """
        print(f"🔍 Quick Search: {query}")
        
        try:
            results = []
            
            # 1. Search using the fast and direct DuckDuckGo API
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=max_results))
            
            if not search_results:
                 print("⚠️ [Warning] No results found from search engine.")
            else:
                 print(f"💡 Found {len(search_results)} URLs, reading content...")

            # 2. Iterate through results and read their content
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
                    
                    # Access the link and extract the full article
                    if extract_text:
                        try:
                            # Use our smart fetch (light HTTP, then browser fallback)
                            html_text = self._smart_fetch(link)
                            main_text = self._extract_main_content(html_text)
                            result_data['full_text'] = main_text[:2000] # Take the first 2000 characters
                        except Exception as inner_e:
                            result_data['full_text'] = f"Failed to extract text: {inner_e}"
                    
                    results.append(result_data)
                except Exception as e:
                    print(f"⚠️ [Parse Error] Failed to process a result item: {e}")
                    continue
            
            return {
                'success': True,
                'query': query,
                'results': results,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Quick search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query
            }

    # =================================================================
    # Mode 2: Deep Research
    # =================================================================
    
    def deep_research(
        self,
        question: str,
        max_sources: int = 3,
        compare_attributes: List[str] = None
    ) -> Dict:
        """
        Multi-step research with comparisons
        
        Example:
            question: "Top 3 UI libraries for React"
            compare_attributes: ["bundle_size", "popularity", "ease_of_use"]
        
        Returns:
            Dict with research findings and comparison
        """
        print(f"🔬 Deep Research: {question}")
        
        research_plan = {
            'question': question,
            'steps': [],
            'findings': [],
            'comparison': None
        }
        
        try:
            # Step 1: Initial search to identify options
            print("  Step 1: Initial search...")
            initial_results = self.quick_search(question, max_results=max_sources)
            
            if not initial_results['success']:
                return initial_results
            
            research_plan['steps'].append({
                'step': 1,
                'action': 'initial_search',
                'results_count': len(initial_results['results'])
            })
            
            # Step 2: Deep dive into each source
            print("  Step 2: Deep dive into sources...")
            for i, source in enumerate(initial_results['results'][:max_sources], 1):
                print(f"    Analyzing source {i}/{max_sources}...")
                
                finding = {
                    'source': source['title'],
                    'link': source['link'],
                    'extracted_data': {}
                }
                
                # Attempt to extract specific attributes
                if compare_attributes and source.get('full_text'):
                    for attr in compare_attributes:
                        # Search for the attribute in the text
                        value = self._extract_attribute(source['full_text'], attr)
                        if value:
                            finding['extracted_data'][attr] = value
                
                research_plan['findings'].append(finding)
            
            research_plan['steps'].append({
                'step': 2,
                'action': 'deep_analysis',
                'sources_analyzed': len(research_plan['findings'])
            })
            
            # Step 3: Compare and synthesize
            print("  Step 3: Comparison and synthesis...")
            if compare_attributes:
                research_plan['comparison'] = self._create_comparison_table(
                    research_plan['findings'],
                    compare_attributes
                )
            
            # Save to memory
            if self.memory:
                self._save_research_to_memory(research_plan)
            
            return {
                'success': True,
                'research_plan': research_plan,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Deep research error: {e}")
            return {
                'success': False,
                'error': str(e),
                'question': question
            }
    
    # =================================================================
    # Mode 3: Active Monitor
    # =================================================================
    
    def setup_monitor(
        self,
        url: str,
        check_selector: str,
        check_interval_hours: int = 6,
        notify_on_change: bool = True,
        task_name: str = None
    ) -> str:
        """
        Set up periodic monitoring for a page
        """
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
        
        # Create a task in memory (if available)
        if self.memory:
            self.memory.create_task(
                title=task_name,
                description=f"Monitor {url} every {check_interval_hours} hours",
                priority=2,
                tags=['browser_monitor', 'automated'],
                related_memory_id=None
            )
        
        print(f"✅ Monitor task created: {task_id}")
        return task_id
    
    def run_monitor_check(self, task_id: str) -> Dict:
        """
        Run a single monitor check
        """
        if task_id not in self.monitoring_tasks:
            return {'success': False, 'error': 'Task not found'}
        
        task = self.monitoring_tasks[task_id]
        print(f"🔍 Running monitor check: {task['task_name']}")
        
        try:
            # Use _smart_fetch so the browser opens if the site is protected
            html_text = self._smart_fetch(task['url'])
            
            if not html_text:
                return {'success': False, 'error': 'Failed to fetch page', 'task_id': task_id}
                
            soup = BeautifulSoup(html_text, 'html.parser')
            element = soup.select_one(task['check_selector'])
            
            if not element:
                return {
                    'success': False,
                    'error': 'Selector not found',
                    'task_id': task_id
                }
            
            current_value = element.get_text(strip=True)
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
            print(f"❌ Monitor check error: {e}")
            return {
                'success': False,
                'error': str(e),
                'task_id': task_id
            }

    # =================================================================
    # Mode 4: Auto Learn
    # =================================================================
    
    def auto_learn(
        self,
        topic: str,
        max_sources: int = 3,
        save_to_memory: bool = True
    ) -> Dict:
        """
        Autonomous learning about a topic and saving it to memory
        """
        print(f"📚 Auto Learning: {topic}")
        
        try:
            # Search for information
            search_results = self.quick_search(
                query=topic,
                max_results=max_sources,
                extract_text=True
            )
            
            if not search_results['success']:
                return search_results
            
            # Synthesize information
            learned_facts = []
            
            for result in search_results['results']:
                if result.get('full_text'):
                    # Extract key facts (simplified)
                    facts = self._extract_key_facts(result['full_text'], topic)
                    learned_facts.extend(facts)
            
            # Save to memory
            if save_to_memory and self.memory:
                # Save as knowledge
                self.memory.store_knowledge(
                    entity=topic,
                    entity_type="concept",
                    attributes={
                        'learned_from': 'auto_learn',
                        'facts': learned_facts,
                        'sources': [r['link'] for r in search_results['results']],
                        'learned_at': datetime.now().isoformat()
                    },
                    confidence=0.8  # Medium confidence (from the internet)
                )
                
                # Save as memory
                self.memory.store_memory(
                    content=f"Learned about {topic}: " + "; ".join(learned_facts[:3]),
                    title=f"Auto-learned: {topic}",
                    memory_type='semantic',
                    importance=7,
                    tags=['auto_learn', topic]
                )
            
            return {
                'success': True,
                'topic': topic,
                'facts_learned': len(learned_facts),
                'facts': learned_facts,
                'sources': [r['link'] for r in search_results['results']],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Auto learn error: {e}")
            return {
                'success': False,
                'error': str(e),
                'topic': topic
            }
    
    # =================================================================
    # Mode 5: RPA Task (Basic)
    # =================================================================
    
    def execute_rpa_task(
        self,
        task_type: Literal["fill_form", "click_button", "download_file"],
        url: str,
        params: Dict
    ) -> Dict:
        """
        Execute a simple RPA task
        """
        print(f"🤖 RPA Task: {task_type} on {url}")
        
        # Note: Scrapling does not support full interaction. Playwright or Selenium is needed for interactive tasks here.
        
        return {
            'success': False,
            'error': 'RPA tasks require Playwright/Selenium - not implemented in basic version',
            'suggestion': 'Use Playwright integration for full RPA capabilities'
        }
    
    # =================================================================
    # Helper Methods
    # =================================================================
    
    def _extract_main_content(self, html_text) -> str:
        """
        Extract main content from the page using BeautifulSoup
        """
        if not html_text:
            return ""
            
        try:
            soup = BeautifulSoup(html_text, 'html.parser')
            
            # Remove scripts and styles to prevent text corruption
            for script in soup(["script", "style"]):
                script.decompose()

            main_selectors = ['article', 'main', '[role="main"]', '.content', '#content']
            
            for selector in main_selectors:
                element = soup.select_one(selector)
                if element:
                    return element.get_text(separator=' ', strip=True)
            
            # fallback: all text in the body
            fallback_element = soup.select_one('body')
            return fallback_element.get_text(separator=' ', strip=True) if fallback_element else soup.get_text(separator=' ', strip=True)
            
        except Exception as e:
            print(f"⚠️ Content extraction error: {e}")
            return ""
    
    def _extract_attribute(self, text: str, attribute: str) -> Optional[str]:
        """
        Extract a specific attribute from the text (simplified)
        """
        import re
        
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
        """
        Extract key facts from the text with a smart fallback to a general summary.
        """
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
        
        # If exact keywords aren't found, pull the first few sentences as a general summary instead of returning empty
        if not relevant_sentences and sentences:
            print(f"💡 No exact keyword matches for '{topic}', falling back to general summary.")
            return sentences[:max_facts]
            
        return relevant_sentences[:max_facts]
    
    def _create_comparison_table(
        self, 
        findings: List[Dict],
        attributes: List[str]
    ) -> Dict:
        """
        Create a comparison table
        """
        comparison = {
            'attributes': attributes,
            'items': []
        }
        
        for finding in findings:
            item = {
                'name': finding['source'],
                'link': finding['link'],
                'attributes': {}
            }
            
            for attr in attributes:
                value = finding['extracted_data'].get(attr, 'N/A')
                item['attributes'][attr] = value
            
            comparison['items'].append(item)
        
        return comparison
    
    def _save_research_to_memory(self, research_plan: Dict):
        """
        Save research findings to memory
        """
        if not self.memory:
            return
        
        # Save as memory
        summary = f"Research on: {research_plan['question']}\n"
        summary += f"Found {len(research_plan['findings'])} sources\n"
        
        if research_plan.get('comparison'):
            summary += "Comparison completed"
        
        self.memory.store_memory(
            content=json.dumps(research_plan, indent=2),
            title=f"Research: {research_plan['question'][:50]}",
            memory_type='episodic',
            importance=8,
            tags=['research', 'browser_agent', 'deep_search']
        )


# =================================================================
# API Interface to communicate with JARVIS
# =================================================================

class BrowserAgentAPI:
    """
    API Interface to communicate with the Browser Agent
    """
    
    def __init__(self, memory_manager=None):
        self.agent = BrowserAgent(memory_manager)
    
    def execute(
        self, 
        mode: BrowserMode,
        params: Dict
    ) -> Dict:
        """
        Execute an operation based on the mode
        """
        try:
            if mode == BrowserMode.QUICK_SEARCH:
                return self.agent.quick_search(**params)
            
            elif mode == BrowserMode.DEEP_RESEARCH:
                return self.agent.deep_research(**params)
            
            elif mode == BrowserMode.ACTIVE_MONITOR:
                action = params.pop('action', 'setup')
                if action == 'setup':
                    task_id = self.agent.setup_monitor(**params)
                    return {'success': True, 'task_id': task_id}
                elif action == 'check':
                    return self.agent.run_monitor_check(params['task_id'])
            
            elif mode == BrowserMode.AUTO_LEARN:
                return self.agent.auto_learn(**params)
            
            elif mode == BrowserMode.RPA_TASK:
                return self.agent.execute_rpa_task(**params)
            
            else:
                return {
                    'success': False,
                    'error': f'Unknown mode: {mode}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'mode': mode
            }


# =================================================================
# System Test
# =================================================================
if __name__ == "__main__":
    print("="*60)
    print("   🌐 JARVIS Browser Agent Test")
    print("="*60)
    
    # Initialize (without memory for testing)
    agent = BrowserAgent(memory_manager=None)
    
    # Test 1: Quick Search
    print("\n1️⃣ Testing Quick Search...")
    result = agent.quick_search("Python latest version", max_results=3)
    print(f"   Found {len(result.get('results', []))} results")
    
    # Test 2: Auto Learn
    print("\n2️⃣ Testing Auto Learn...")
    result = agent.auto_learn("React hooks", max_sources=2, save_to_memory=False)
    print(f"   Learned {result.get('facts_learned', 0)} facts")
    
    # Test 3: Setup Monitor
    print("\n3️⃣ Testing Monitor Setup...")
    task_id = agent.setup_monitor(
        url="https://example.com",
        check_selector="h1",
        check_interval_hours=6,
        task_name="Example Monitor"
    )
    print(f"   Monitor task created: {task_id}")

    # Test 4: Fallback Stealth Browser Test
    print("\n4️⃣ Testing Stealthy Browser (Fallback Plan) - Direct Execution...")
    try:
        print(f"   🕵️ Executing Camoufox directly from: {CAMOUFOX_BROWSER_PATH}")
        from patchright.sync_api import sync_playwright
        
        path_str = str(CAMOUFOX_BROWSER_PATH) if CAMOUFOX_BROWSER_PATH else None
        if path_str and os.path.exists(path_str):
            with sync_playwright() as p:
                browser = p.firefox.launch(executable_path=path_str, headless=True)
                page = browser.new_page()
                print("   🌐 Testing fetch on protected site (nowsecure.nl)...")
                response = page.goto("https://nowsecure.nl/")
                print(f"   ✅ Stealth Browser initialized successfully.")
                print(f"   Status Code: {response.status if response else 'Unknown'} (200 means success!)")
                browser.close()
        else:
            print(f"   ❌ Executable not found at {path_str}")
            
    except Exception as e:
        print(f"   ❌ Stealth Browser test failed: {e}")
    
    print("\n✅ Browser Agent test complete!")