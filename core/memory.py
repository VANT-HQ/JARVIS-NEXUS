# core/memory.py
"""
JARVIS Advanced Memory System
==============================

Multi-layered Memory System:
1. Working Memory    - Current context and active conversation.
2. Episodic Memory   - Interaction history and events.
3. Semantic Memory   - Knowledge base and factual information.
4. Procedural Memory - Task management and to-do execution.

Features:
- Smart indexing with keywords and embeddings
- Temporal decay
- Memory consolidation
- Context-aware retrieval
- Strict State Machine for Task Management
- Thread-safe DB operations (Mutex Locks)
- Background Context Syncing
- Consolidated Memory Entry Point (save_to_memory)
"""

import sqlite3
import json
import time
import logging
import sys
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from enum import Enum

from core.config import DB_PATH, CACHE_DIR, get_setting

import requests
import numpy as np
try:
    import faiss  
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("   [Memory] ⚠️ Warning: faiss not installed. Using keyword search only.")
    logging.warning("[Memory] faiss not installed. Using keyword search only.")

# =====================================================================
# State Machine Enums (Strict Task Management)
# =====================================================================
class TaskStatus(Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

    @classmethod
    def is_valid_transition(cls, current_status: str, new_status: str) -> bool:
        """
        Prevents invalid transitions. Cannot modify a task that has 
        reached a terminal state.
        """
        terminal_states = [cls.COMPLETED.value, cls.FAILED.value, cls.STOPPED.value]
        if current_status in terminal_states:
            return False
        return True

# =====================================================================
# Main Memory Manager Class
# =====================================================================
class MemoryManager: #? (Hmody: for the records, my midterm tomorrow and im here)
    def get_ollama_embedding(self, text: str) -> np.ndarray:
        """Talks to Ollama to convert text into embeddings (Vectors) based on user settings"""
        try:
            model = get_setting("embedding_model", "all-minilm")
            base_url = get_setting("local_api_url", "http://localhost:11434")
            api_url = f"{base_url.rstrip('/')}/api/embeddings"
            
            response = requests.post(api_url, json={
                "model": model,
                "prompt": text
            })
            if response.status_code == 200:
                embedding = response.json()["embedding"]
                vec = np.array([embedding], dtype=np.float32)
                faiss.normalize_L2(vec)
                return vec
        except Exception as e:
            print(f"   [Memory] ❌ Ollama Embedding Error: {e}")
            logging.error(f"[Memory] Ollama Embedding Error: {e}")
        return None
    def __init__(self):
        self.db_lock = threading.Lock()
        self.ram_upcoming_tasks = []
        
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        
        # Ensure tables are created every time we start
        with self.db_lock:
            self.create_tables()
            
        # Set FAISS index path
        self.faiss_index_path = CACHE_DIR / "faiss_index.bin"
        self.faiss_index = None

        if EMBEDDINGS_AVAILABLE:
            model = get_setting("embedding_model", "all-minilm")
            print(f"   [Memory] ✅ Embeddings configured via Ollama ({model})")
            self.embedding_model = True
            try:
                # Do a test request to dynamically determine dimension
                test_vec = self.get_ollama_embedding("test")
                if test_vec is not None:
                    dim = test_vec.shape[1]
                else:
                    dim = 384 # Fallback
                
                if self.faiss_index_path.exists():
                    self.faiss_index = faiss.read_index(str(self.faiss_index_path))
                    # Check dimension match
                    if self.faiss_index.d != dim:
                        print(f"   [Memory] ⚠️ FAISS Index dimension mismatch (was {self.faiss_index.d}, now {dim}). Recreating...")
                        logging.warning(f"[Memory] FAISS Index dimension mismatch (was {self.faiss_index.d}, now {dim}). Recreating...")
                        self.faiss_index_path.unlink()
                        base_index = faiss.IndexFlatIP(dim)
                        self.faiss_index = faiss.IndexIDMap(base_index)
                        self._rebuild_faiss_index()
                    else:
                        print("   [Memory] ⚡ FAISS Index loaded from disk.")
                else:
                    base_index = faiss.IndexFlatIP(dim)
                    self.faiss_index = faiss.IndexIDMap(base_index)
                    print("   [Memory] ⚡ New FAISS Index initialized.")
                    self._rebuild_faiss_index()
            except Exception as e:
                print(f"   [Memory] ❌ Failed to initialize FAISS: {e}")
                logging.error(f"[Memory] Failed to initialize FAISS: {e}")
                self.embedding_model = None
        else:
            self.embedding_model = None

    def _rebuild_faiss_index(self):
        """Rebuilds the entire FAISS index from the database SQLite records in the background."""
        print("   [Memory] 🔄 Rebuilding FAISS Index from DB...")
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT memory_id, full_content FROM memory_details")
            rows = cursor.fetchall()
            
            if not rows:
                print("   [Memory] ℹ️ DB is empty, nothing to rebuild.")
                return
            
            for row in rows:
                memory_id, content = row
                vec = self.get_ollama_embedding(content)
                if vec is not None:
                    self.faiss_index.add_with_ids(vec, np.array([memory_id], dtype=np.int64))
            
            faiss.write_index(self.faiss_index, str(self.faiss_index_path))
            print(f"   [Memory] ✅ Rebuilt index with {len(rows)} entries.")
        except Exception as e:
            print(f"   [Memory] ❌ Error rebuilding FAISS index: {e}")
            logging.error(f"[Memory] Error rebuilding FAISS index: {e}")
        
        # Safely create database tables
        with self.db_lock:
            self.create_tables()
            
        print("   [Memory] 🧠 Memory System initialized (Pure Storage Engine)")

    # =================================================================
    # Database Schema
    # =================================================================
    def create_tables(self):
        """Build the complete database schema (must be called within db_lock)."""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS working_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                memory_type TEXT DEFAULT 'conversation',
                timestamp REAL NOT NULL,
                expires_at REAL,
                importance INTEGER DEFAULT 1,
                tags TEXT,
                related_to INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cron_registry (
                cron_id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_expression TEXT NOT NULL,
                action_prompt TEXT NOT NULL,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                last_run_at REAL,
                run_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                keywords TEXT NOT NULL,
                summary TEXT,
                memory_type TEXT DEFAULT 'episodic',
                timestamp REAL NOT NULL,
                last_accessed REAL,
                access_count INTEGER DEFAULT 0,
                importance_score REAL DEFAULT 1.0,
                embedding BLOB,
                tags TEXT,
                related_memories TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_details (
                memory_id INTEGER PRIMARY KEY,
                full_content TEXT NOT NULL,
                metadata TEXT,
                created_at REAL NOT NULL,
                updated_at REAL,
                FOREIGN KEY(memory_id) REFERENCES memory_index(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT NOT NULL,
                entity_type TEXT,
                attributes TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source_memory_id INTEGER,
                created_at REAL NOT NULL,
                updated_at REAL,
                FOREIGN KEY(source_memory_id) REFERENCES memory_index(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                priority INTEGER DEFAULT 2,
                status TEXT DEFAULT 'created',
                due_date REAL,
                created_at REAL NOT NULL,
                completed_at REAL,
                parent_task_id INTEGER,
                recurrence TEXT,
                related_memory_id INTEGER,
                tags TEXT,
                FOREIGN KEY(parent_task_id) REFERENCES tasks(id),
                FOREIGN KEY(related_memory_id) REFERENCES memory_index(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain_name TEXT,
                memory_ids TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_stats (
                date TEXT PRIMARY KEY,
                total_memories INTEGER DEFAULT 0,
                memories_created INTEGER DEFAULT 0,
                memories_accessed INTEGER DEFAULT 0,
                most_accessed_topic TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords ON memory_index(keywords)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON memory_index(timestamp DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags ON memory_index(tags)')
        
        self.conn.commit()

    # =================================================================
    # Consolidated Memory Operations (The New Entry Point)
    # =================================================================
    def save_to_memory(self, content: str, category: str = 'event', tags: List[str] = None) -> int:
        """
        Consolidated Memory Engine: Determines where to store information 
        and routes it to the appropriate structural table.
        Supported categories: fact, preference, event, deep_search
        """
        tags = tags or []
        category = category.lower()
        
        if category == 'fact':
            entity_name = self._extract_keywords(content, max_keywords=2)
            if not entity_name:
                entity_name = "General Fact"
                
            attributes = {"details": content, "source": "save_to_memory"}
            return self._store_knowledge(
                entity=entity_name.title(),
                entity_type="fact",
                attributes=attributes,
                confidence=1.0
            )
        
        elif category == 'deep_search':
            # Isolate deep search data and lower its importance to prevent polluting personal episodic memory
            importance = 2
            tags.extend(["deep_search", "web_data"])
            title_preview = content[:30] + "..." if len(content) > 30 else content
            return self.store_memory(
                content=content,
                title=f"Deep Search: {title_preview}",
                memory_type='semantic',
                importance=importance,
                tags=tags
            )
            
        else:
            importance = 8 if category == 'preference' else 5
            tags.extend([category, "user_provided"])
            title_preview = content[:30] + "..." if len(content) > 30 else content
            return self.store_memory(
                content=content,
                title=f"User {category.capitalize()}: {title_preview}",
                memory_type='episodic',
                importance=importance,
                tags=tags
            )

    # =================================================================
    # Core Memory Operations (Episodic)
    # =================================================================
    def store_memory(self, content: str, title: str = None, memory_type: str = 'episodic',
                     importance: int = 5, tags: List[str] = None, metadata: Dict = None) -> int:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                keywords = self._extract_keywords(content)
                summary = self._create_summary(content, max_length=200)
                
                if not title:
                    title = summary[:50] + "..." if len(summary) > 50 else summary
                
                timestamp = time.time()
                tags_json = json.dumps(tags or [])
                
                # The BLOB field remains in the database as a backup, but primary reliance is on FAISS
                cursor.execute('''
                    INSERT INTO memory_index 
                    (title, keywords, summary, memory_type, timestamp, last_accessed, 
                     importance_score, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (title, keywords, summary, memory_type, timestamp, timestamp, float(importance), tags_json))
                
                memory_id = cursor.lastrowid
                
                # Insert the vector into FAISS
                if self.embedding_model and self.faiss_index is not None:
                    embedding_vector = self.get_ollama_embedding(content)
                    if embedding_vector is not None:
                        faiss_id = np.array([memory_id], dtype=np.int64)
                        self.faiss_index.add_with_ids(embedding_vector, faiss_id)
                    # Save the index after modification to ensure data persistence
                    faiss.write_index(self.faiss_index, str(self.faiss_index_path))
                
                metadata_json = json.dumps(metadata or {})
                cursor.execute('''
                    INSERT INTO memory_details 
                    (memory_id, full_content, metadata, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (memory_id, content, metadata_json, timestamp))
                
                self.conn.commit()
                self._update_stats('memory_created', cursor)
                
                print(f"   [Memory] 💾 Stored memory #{memory_id}: {title}")
                return memory_id
                
            except Exception as e:
                print(f"   [Memory] ❌ Error storing memory: {e}")
                logging.error(f"[Memory] Error storing memory: {e}")
                return -1

    def recall_memory(self, query: str, limit: int = 5, memory_type: str = None, 
                      min_importance: float = 0.0, use_semantic: bool = True) -> List[Dict]:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                memories = []
                if use_semantic and self.embedding_model:
                    memories = self._semantic_search(query, limit, memory_type, min_importance, cursor)
                
                if not memories:
                    memories = self._keyword_search(query, limit, memory_type, min_importance, cursor)
                
                for memory in memories:
                    self._update_access_stats(memory['id'], cursor)
                
                self._update_stats('memory_accessed', cursor)
                return memories
                
            except Exception as e:
                print(f"   [Memory] ❌ Error recalling memory: {e}")
                logging.error(f"[Memory] Error recalling memory: {e}")
                return []

    def get_memory_details(self, memory_id: int) -> Optional[Dict]:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT mi.*, md.full_content, md.metadata
                    FROM memory_index mi
                    JOIN memory_details md ON mi.id = md.memory_id
                    WHERE mi.id = ?
                ''', (memory_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                
                self._update_access_stats(memory_id, cursor)
                return self._row_to_dict_with_cursor(row, cursor)
            except Exception as e:
                print(f"   [Memory] ❌ Error getting memory details: {e}")
                logging.error(f"[Memory] Error getting memory details: {e}")
                return None

    # =================================================================
    # Working Memory (Context Window)
    # =================================================================
    def add_to_working_memory(self, content: str, memory_type: str = 'conversation',
                              expires_in_seconds: int = 3600, importance: int = 5, tags: List[str] = None) -> int:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                timestamp = time.time()
                expires_at = timestamp + expires_in_seconds
                tags_json = json.dumps(tags or [])
                
                cursor.execute('''
                    INSERT INTO working_memory 
                    (content, memory_type, timestamp, expires_at, importance, tags)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (content, memory_type, timestamp, expires_at, importance, tags_json))
                self.conn.commit()
                return cursor.lastrowid
            except Exception as e:
                print(f"   [Memory] ❌ Error adding to working memory: {e}")
                logging.error(f"[Memory] Error adding to working memory: {e}")
                return -1

    def get_working_memory(self, limit: int = 10) -> List[Dict]:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                current_time = time.time()
                cursor.execute('DELETE FROM working_memory WHERE expires_at < ?', (current_time,))
                cursor.execute('''
                    SELECT * FROM working_memory 
                    WHERE expires_at > ?
                    ORDER BY importance DESC, timestamp DESC LIMIT ?
                ''', (current_time, limit))
                
                rows = cursor.fetchall()
                self.conn.commit()
                return [self._row_to_dict_with_cursor(row, cursor) for row in rows]
            except Exception as e:
                print(f"   [Memory] ❌ Error getting working memory: {e}")
                logging.error(f"[Memory] Error getting working memory: {e}")
                return []

    def clear_working_memory(self):
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM working_memory')
                self.conn.commit()
                print("   [Memory] 🗑️ Working memory cleared")
            except Exception as e:
                print(f"   [Memory] ❌ Error clearing working memory: {e}")
                logging.error(f"[Memory] Error clearing working memory: {e}")

    # =================================================================
    # Knowledge Base (Semantic Memory)
    # =================================================================
    def _store_knowledge(self, entity: str, entity_type: str, attributes: Dict, 
                         confidence: float = 1.0, source_memory_id: int = None) -> int:
        """
        Internal private method. Called automatically via save_to_memory.
        """
        fact_content = f"Knowledge Base Fact -> Entity: {entity}, Type: {entity_type}. Details: {json.dumps(attributes, ensure_ascii=False)}"
        fact_title = f"Fact: {entity}"
        
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT id, attributes FROM knowledge_base 
                    WHERE entity = ? AND entity_type = ?
                ''', (entity, entity_type))
                existing = cursor.fetchone()
                timestamp = time.time()
                
                if existing:
                    existing_id, existing_attrs = existing
                    existing_attrs_dict = json.loads(existing_attrs)
                    existing_attrs_dict.update(attributes)
                    
                    cursor.execute('''
                        UPDATE knowledge_base 
                        SET attributes = ?, confidence = ?, updated_at = ?
                        WHERE id = ?
                    ''', (json.dumps(existing_attrs_dict), confidence, timestamp, existing_id))
                    entity_id = existing_id
                    print(f"   [Memory] 🔄 Updated knowledge: {entity}")
                else:
                    cursor.execute('''
                        INSERT INTO knowledge_base 
                        (entity, entity_type, attributes, confidence, source_memory_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (entity, entity_type, json.dumps(attributes), confidence, source_memory_id, timestamp))
                    entity_id = cursor.lastrowid
                    print(f"   [Memory] 💡 Stored knowledge: {entity}")
                
                self.conn.commit()
                
            except Exception as e:
                print(f"   [Memory] ❌ Error storing knowledge: {e}")
                logging.error(f"[Memory] Error storing knowledge: {e}")
                return -1

        # Triggers episodic tracking (Executed outside db_lock because store_memory enforces its own lock)
        self.store_memory(
            content=fact_content, title=fact_title, memory_type='semantic', 
            importance=8, tags=['knowledge_base', str(entity_type)]
        )
        return entity_id

    def query_knowledge(self, entity: str = None, entity_type: str = None) -> List[Dict]:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                query = "SELECT * FROM knowledge_base WHERE 1=1"
                params = []
                
                if entity:
                    query += " AND entity LIKE ?"
                    params.append(f"%{entity}%")
                if entity_type:
                    query += " AND entity_type = ?"
                    params.append(entity_type)
                    
                query += " ORDER BY confidence DESC, updated_at DESC"
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._row_to_dict_with_cursor(row, cursor) for row in rows]
            except Exception as e:
                print(f"   [Memory] ❌ Error querying knowledge: {e}")
                logging.error(f"[Memory] Error querying knowledge: {e}")
                return []

    # =================================================================
    # Task Management System (Procedural Memory)
    # =================================================================
    def create_task(self, title: str, description: str = None, priority: int = 3, 
                    time_type: str = "none",
                    delay_minutes: int = 0, delay_hours: int = 0, delay_days: int = 0,
                    absolute_date: str = None, absolute_time: str = None,
                    tags: List[str] = None, parent_task_id: int = None, related_memory_id: int = None) -> int:
        
        # [Defensive Programming] Protect priority value
        try:
            priority = int(priority)
        except (ValueError, TypeError):
            p_str = str(priority).lower()
            if 'high' in p_str or '1' in p_str: priority = 1
            elif 'low' in p_str or '3' in p_str: priority = 3
            else: priority = 2  # Default to Medium
            
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                timestamp = time.time()
                now = datetime.now()
                due_timestamp = None
                
                # Time Engine Calculation Logic
                if time_type == "relative":
                    # If relative time is provided (e.g., "after X time")
                    delay = timedelta(
                        minutes=int(delay_minutes or 0), 
                        hours=int(delay_hours or 0), 
                        days=int(delay_days or 0)
                    )
                    if delay.total_seconds() > 0:
                        due_timestamp = (now + delay).timestamp()

                elif time_type == "absolute":
                    # If absolute date/time is provided
                    target_date_str = absolute_date if absolute_date else now.strftime("%Y-%m-%d")
                    
                    # Default to 09:00 AM for reminders if no time is specified
                    target_time_str = absolute_time if absolute_time else "09:00" 
                    
                    try:
                        dt_str = f"{target_date_str} {target_time_str}"
                        target_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                        
                        # If the requested time has passed today, automatically move it to tomorrow
                        if target_dt < now and not absolute_date:
                            target_dt += timedelta(days=1)
                            
                        due_timestamp = target_dt.timestamp()
                    except ValueError as e:
                        print(f"   [Memory] ⚠️ Failed to parse absolute time: {e}")
                        logging.warning(f"[Memory] Failed to parse absolute time: {e}")

                tags_json = json.dumps(tags or [])
                
                cursor.execute('''
                    INSERT INTO tasks 
                    (title, description, priority, status, due_date, created_at, 
                     parent_task_id, tags, related_memory_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (title, description, priority, TaskStatus.CREATED.value, due_timestamp, timestamp, 
                      parent_task_id, tags_json, related_memory_id))
                
                task_id = cursor.lastrowid
                self.conn.commit()
                
                due_str = datetime.fromtimestamp(due_timestamp).strftime('%Y-%m-%d %H:%M') if due_timestamp else "No due date"
                print(f"   [Memory] ✅ Task created #{task_id}: {title} (Due: {due_str})")
                return task_id
            except Exception as e:
                print(f"   [Memory] ❌ Error creating task: {e}")
                logging.error(f"[Memory] Error creating task: {e}")
                return -1

    def modify_task(self, task_id: int, new_status: str = None, new_title: str = None, new_priority: int = None) -> bool:
        
        # [Defensive Programming] Protect priority value
        if new_priority is not None:
            try:
                new_priority = int(new_priority)
            except (ValueError, TypeError):
                p_str = str(new_priority).lower()
                if 'high' in p_str or '1' in p_str: new_priority = 1
                elif 'low' in p_str or '3' in p_str: new_priority = 3
                else: new_priority = 2

        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('SELECT status FROM tasks WHERE id = ?', (task_id,))
                row = cursor.fetchone()
                
                if not row:
                    print(f"   [Memory] ⚠️ Task #{task_id} not found.")
                    logging.warning(f"[Memory] Task #{task_id} not found.")
                    return False
                    
                current_status = row[0]
                updates = []
                params = []

                if new_status:
                    valid_states = [e.value for e in TaskStatus]
                    if new_status not in valid_states:
                        print(f"   [Memory] ❌ Invalid status: {new_status}")
                        logging.error(f"[Memory] Invalid status: {new_status}")
                        return False
                        
                    if not TaskStatus.is_valid_transition(current_status, new_status):
                        print(f"   [Memory] ⛔ Cannot transition task #{task_id} from '{current_status}' to '{new_status}'.")
                        logging.error(f"[Memory] Cannot transition task #{task_id} from '{current_status}' to '{new_status}'.")
                        return False
                        
                    updates.append("status = ?")
                    params.append(new_status)
                    
                    if new_status == TaskStatus.COMPLETED.value:
                        updates.append("completed_at = ?")
                        params.append(time.time())

                if new_title:
                    updates.append("title = ?")
                    params.append(new_title)
                if new_priority is not None:
                    updates.append("priority = ?")
                    params.append(new_priority)

                if not updates:
                    return False

                params.append(task_id)
                query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, tuple(params))
                self.conn.commit()
                
                print(f"   [Memory] ✏️ Task #{task_id} updated successfully.")
                
            except Exception as e:
                print(f"   [Memory] ❌ Error modifying task: {e}")
                logging.error(f"[Memory] Error modifying task: {e}")
                return False

        self.sync_upcoming_tasks()
        return True

    def get_tasks(self, status: str = TaskStatus.CREATED.value, priority_min: int = None, limit: int = None) -> List[Dict]:
        with self.db_lock:
            try:
                cursor = self.conn.cursor()
                query = "SELECT * FROM tasks WHERE status = ?"
                params = [status]
                
                if priority_min:
                    query += " AND priority <= ?"
                    params.append(priority_min)
                    
                query += " ORDER BY priority ASC, due_date ASC"
                if limit:
                    query += f" LIMIT {limit}"
                    
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._row_to_dict_with_cursor(row, cursor) for row in rows]
            except Exception as e:
                print(f"   [Memory] ❌ Error getting tasks: {e}")
                logging.error(f"[Memory] Error getting tasks: {e}")
                return []

    # =================================================================
    # RAM Sync & Autonomous Context Injector
    # =================================================================
    def sync_upcoming_tasks(self):
        """
        Fetches upcoming tasks into RAM for fast access.
        Now called via WatchDog instead of running a dedicated thread inside memory.
        """
        try:
            current_time = time.time()
            future_time = current_time + (48 * 3600)
            
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM tasks 
                    WHERE status = ? AND due_date IS NOT NULL 
                    AND due_date BETWEEN ? AND ?
                    ORDER BY due_date ASC
                ''', (TaskStatus.CREATED.value, current_time, future_time))
                
                rows = cursor.fetchall()
                self.ram_upcoming_tasks = [self._row_to_dict_with_cursor(row, cursor) for row in rows]
        except Exception as e:
            print(f"   [Memory] ❌ Error syncing tasks: {e}")
            logging.error(f"[Memory] Error syncing tasks: {e}")
            
    def get_time_aware_context(self) -> str:
        """
        Injects task context into the System Prompt (24h past & 48h future).
        """
        try:
            current_time = time.time()
            past_24h = current_time - (24 * 3600)
            future_48h = current_time + (48 * 3600)
            
            context_string = "--- TIME-AWARE TASK CONTEXT ---\n"
            
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT title, due_date, status, priority FROM tasks 
                    WHERE due_date BETWEEN ? AND ?
                    ORDER BY due_date ASC
                ''', (current_time, future_48h))
                
                upcoming = cursor.fetchall()
                if upcoming:
                    context_string += "[UPCOMING TASKS (Next 48h)]:\n"
                    for row in upcoming:
                        due = datetime.fromtimestamp(row[1]).strftime('%Y-%m-%d %H:%M')
                        context_string += f"- [{row[2].upper()}] Priority {row[3]}: {row[0]} (Due: {due})\n"
                
                cursor.execute('''
                    SELECT title, completed_at, status FROM tasks 
                    WHERE (completed_at BETWEEN ? AND ?) OR (created_at BETWEEN ? AND ?)
                    ORDER BY created_at DESC LIMIT 5
                ''', (past_24h, current_time, past_24h, current_time))
                
                recent = cursor.fetchall()
                if recent:
                    context_string += "\n[RECENTLY MODIFIED/COMPLETED TASKS (Last 24h)]:\n"
                    for row in recent:
                        context_string += f"- [{row[2].upper()}] {row[0]}\n"
                        
            return context_string if (upcoming or recent) else ""
        except Exception:
            return ""

    # =================================================================
    # Internal Helper Methods
    # =================================================================
    def _extract_keywords(self, text: str, max_keywords: int = 10) -> str:
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by'}
        words = re.findall(r'\b\w+\b', text.lower())
        word_freq = {}
        for word in words:
            if word not in stop_words and len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return ' '.join([word for word, _ in sorted_words[:max_keywords]])

    def _create_summary(self, text: str, max_length: int = 200) -> str:
        if len(text) <= max_length:
            return text
        sentences = re.split(r'[.!?]+', text)
        summary = ""
        for sentence in sentences:
            if len(summary) + len(sentence) <= max_length:
                summary += sentence + ". "
            else:
                break
        return summary.strip()

    def _semantic_search(self, query: str, limit: int, memory_type: str, min_importance: float, cursor) -> List[Dict]:
        if not self.embedding_model or self.faiss_index is None:
            return []
        
        try:
            # Search via FAISS and fetch a slightly larger pool for re-ranking based on priority/importance
            fetch_limit = limit * 4 
            query_embedding = self.get_ollama_embedding(query)
            if query_embedding is None:
                return []
            
            distances, indices = self.faiss_index.search(query_embedding, fetch_limit)
            
            # Filter valid IDs
            valid_ids = [int(idx) for idx in indices[0] if idx != -1]
            if not valid_ids:
                return []
                
            # Fetch data from SQLite using extracted IDs
            placeholders = ','.join('?' for _ in valid_ids)
            sql = f"""
                SELECT mi.*, md.full_content, md.metadata 
                FROM memory_index mi 
                LEFT JOIN memory_details md ON mi.id = md.memory_id 
                WHERE mi.id IN ({placeholders})
            """
            params = valid_ids.copy()
            
            if memory_type:
                sql += " AND mi.memory_type = ?"
                params.append(memory_type)
            if min_importance > 0:
                sql += " AND mi.importance_score >= ?"
                params.append(min_importance)
                
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            # Combine FAISS distance with importance weighting (Priority Weighting)
            results = []
            for row in rows:
                memory_dict = self._row_to_dict_with_cursor(row, cursor)
                memory_id = memory_dict['id']
                importance = float(memory_dict.get('importance_score', 1.0))
                
                # Find original distance from FAISS output
                idx_pos = valid_ids.index(memory_id)
                base_similarity = float(distances[0][idx_pos])
                
                # Weighting formula: Boost score for important data (like preferences with score = 8)
                weighted_score = base_similarity * (1.0 + (importance * 0.15))
                memory_dict['similarity_score'] = weighted_score
                
                results.append(memory_dict)
            
            # Final sorting based on weighted result rather than semantic similarity alone
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            return results[:limit]
            
        except Exception as e:
            print(f"   [Memory] ❌ Error in semantic search: {e}")
            return []

    def _keyword_search(self, query: str, limit: int, memory_type: str, min_importance: float, cursor) -> List[Dict]:
        stop_words = {'what', 'is', 'the', 'project', 'tell', 'me', 'about', 'who', 'how', 'a', 'an', 'in', 'on', 'at', 'do', 'i', 'prefer', 'using', 'and', 'or', 'but', 'for', 'with', 'to', 'of', 'from'}
        
        # Clean and extract words securely
        raw_words = re.findall(r'\b\w+\b', query.lower())
        words = [w for w in raw_words if w not in stop_words and len(w) > 2]
        
        if not words:
            words = [query.lower().strip()]
            
        sql_select = """
            SELECT mi.*, md.full_content, md.metadata,
            (
        """
        scoring_cases = []
        conditions = []
        score_params = [] 
        where_params = []
        
        for word in words:
            conditions.append("(mi.keywords LIKE ? OR mi.title LIKE ? OR mi.summary LIKE ? OR md.full_content LIKE ?)")
            where_params.extend([f"%{word}%", f"%{word}%", f"%{word}%", f"%{word}%"])
            
            # Weighted Scoring Mechanism
            scoring_cases.append("""
                (CASE WHEN mi.title LIKE ? THEN 20 ELSE 0 END) +
                (CASE WHEN mi.keywords LIKE ? THEN 15 ELSE 0 END) +
                (CASE WHEN mi.summary LIKE ? THEN 10 ELSE 0 END) +
                (CASE WHEN md.full_content LIKE ? THEN 5 ELSE 0 END)
            """)
            score_params.extend([f"%{word}%", f"%{word}%", f"%{word}%", f"%{word}%"])
            
        sql_select += " + ".join(scoring_cases) + " ) AS search_score "
        
        sql_from = """
            FROM memory_index mi 
            LEFT JOIN memory_details md ON mi.id = md.memory_id 
            WHERE 
        """
        
        sql_where = "(" + " OR ".join(conditions) + ")"
        
        if memory_type:
            sql_where += " AND mi.memory_type = ?"
            where_params.append(memory_type)
            
        if min_importance > 0:
            sql_where += " AND mi.importance_score >= ?"
            where_params.append(min_importance)
            
        sql_order = " ORDER BY (search_score * mi.importance_score) DESC, mi.timestamp DESC LIMIT ?"
        
        final_sql = sql_select + sql_from + sql_where + sql_order
        final_params = score_params + where_params + [limit]
        
        try:
            cursor.execute(final_sql, final_params)
            rows = cursor.fetchall()
            return [self._row_to_dict_with_cursor(row, cursor) for row in rows]
        except Exception as e:
            print(f"   [Memory] ❌ Database error during keyword search: {e}")
            return []

    def _update_access_stats(self, memory_id: int, cursor):
        try:
            cursor.execute('''
                UPDATE memory_index 
                SET last_accessed = ?, access_count = access_count + 1
                WHERE id = ?
            ''', (time.time(), memory_id))
        except Exception:
            pass

    def _update_stats(self, stat_type: str, cursor):
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('INSERT OR IGNORE INTO memory_stats (date) VALUES (?)', (today,))
            
            if stat_type == 'memory_created':
                cursor.execute('''
                    UPDATE memory_stats 
                    SET total_memories = total_memories + 1, memories_created = memories_created + 1
                    WHERE date = ?
                ''', (today,))
            elif stat_type == 'memory_accessed':
                cursor.execute('''
                    UPDATE memory_stats 
                    SET memories_accessed = memories_accessed + 1
                    WHERE date = ?
                ''', (today,))
        except Exception:
            pass

    def _row_to_dict_with_cursor(self, row, cursor) -> Dict:
        if not row:
            return {}
        columns = [desc[0] for desc in cursor.description]
        result = dict(zip(columns, row))
        for key in ['tags', 'metadata', 'attributes', 'related_memories']:
            if key in result and result[key]:
                try:
                    result[key] = json.loads(result[key])
                except Exception:
                    pass
        return result

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass