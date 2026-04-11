# core/memory_manager.py
"""
JARVIS Advanced Memory System
==============================

Multi-layered Memory System:
1. Working Memory - (Current context window)
2. Episodic Memory - (Events, conversations, interactions)
3. Semantic Memory - (Facts, knowledge base)
4. Procedural Memory - (Tasks, TODO lists)

Features:
- Smart indexing with keywords and embeddings
- Temporal decay (Older memories weaken over time)
- Memory consolidation (Merging similar memories)
- Context-aware retrieval (Smart fetching based on context)
- Memory chains (Linking related memories)
"""

import sqlite3
import json
import time
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import hashlib

# =================================================================
# Attempt to import sentence-transformers for embeddings
# =================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    # Import paths directly from the config file
    from core.config import DB_PATH, DEFAULT_EMBEDDING_MODEL as MODEL_PATH
except ImportError:
    print(f"   [Memory] Warning: Could not find config. Using defaults.")

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    print("   [Memory] Warning: sentence-transformers not installed. Using keyword search only.")
    print("   [Memory] Install with: pip install sentence-transformers")

# =================================================================
# Dynamic Path Configurations (Independent for Testing)
# =================================================================
import sys
from pathlib import Path

# Add the main project path so it can read the core folder if this file is run independently
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.config import DB_PATH, DEFAULT_EMBEDDING_MODEL
    MODEL_PATH = DEFAULT_EMBEDDING_MODEL
except (ImportError, AttributeError):
    print(f"   [Memory] Warning: Using default emergency paths.")

class MemoryManager:
    def __init__(self):
        # Ensure the directory exists
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Load the embeddings model (if available)
        if EMBEDDINGS_AVAILABLE:
            print(f"   [Memory] Loading embedding model from: {MODEL_PATH}")
            
        if EMBEDDINGS_AVAILABLE:
            # Convert MODEL_PATH to a Path object to ensure .exists() and .is_dir() work
            model_path_obj = Path(MODEL_PATH)
            
            print(f"   [Memory] Loading embedding model from: {model_path_obj}")
            
            # Ensure the folder exists before attempting to load
            if model_path_obj.exists() and model_path_obj.is_dir():
                try:
                    # Pass the path as a string to the library
                    self.embedding_model = SentenceTransformer(str(model_path_obj), local_files_only=True)
                    print("   [Memory] ✅ Embeddings ready for semantic search (100% Offline)")
                except Exception as e:
                    print(f"   [Memory] ❌ Failed to load model offline from {model_path_obj}")
                    print(f"   [Memory] Error details: {e}")
                    self.embedding_model = None
            else:
                print(f"   [Memory] ⚠️ Offline model folder not found at: {model_path_obj}")
                self.embedding_model = None
        else:
            self.embedding_model = None
        
        self.create_tables()
        print("   [Memory] 🧠 Memory System initialized")

    # =================================================================
    # Database Schema
    # =================================================================
    
    def create_tables(self):
        """
        Build the complete database structure
        """
        
        # 1. Working Memory - Current context
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS working_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                memory_type TEXT DEFAULT 'conversation',  -- conversation, fact, note
                timestamp REAL NOT NULL,
                expires_at REAL,  -- When this memory expires
                importance INTEGER DEFAULT 1,  -- 1-10
                tags TEXT,  -- JSON array of tags
                related_to INTEGER  -- ID of related long-term memory
            )
        ''')
        
        # 2. Long-term Memory Index - For rapid searching
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                keywords TEXT NOT NULL,  -- Keywords for search
                summary TEXT,  -- Short summary (max 200 chars)
                memory_type TEXT DEFAULT 'episodic',  -- episodic, semantic, procedural
                timestamp REAL NOT NULL,
                last_accessed REAL,  -- Last time the memory was accessed
                access_count INTEGER DEFAULT 0,  -- Number of retrievals
                importance_score REAL DEFAULT 1.0,  -- Changes over time
                embedding BLOB,  -- Vector embedding (if available)
                tags TEXT,  -- JSON array
                related_memories TEXT  -- JSON array of related memory IDs
            )
        ''')
        
        # 3. Memory Details - Full content payload
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_details (
                memory_id INTEGER PRIMARY KEY,
                full_content TEXT NOT NULL,
                metadata TEXT,  -- JSON with extra info
                created_at REAL NOT NULL,
                updated_at REAL,
                FOREIGN KEY(memory_id) REFERENCES memory_index(id) ON DELETE CASCADE
            )
        ''')
        
        # 4. Semantic Memory / Knowledge Base
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity TEXT NOT NULL,  -- Name of the entity (person, place, concept)
                entity_type TEXT,  -- person, location, concept, skill, etc.
                attributes TEXT NOT NULL,  -- JSON dict of properties
                confidence REAL DEFAULT 1.0,  -- Confidence level in this fact
                source_memory_id INTEGER,  -- Where this info originated
                created_at REAL NOT NULL,
                updated_at REAL,
                FOREIGN KEY(source_memory_id) REFERENCES memory_index(id)
            )
        ''')
        
        # 5. Procedural Memory / Tasks (TODO System)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                priority INTEGER DEFAULT 2,  -- 1=critical, 2=high, 3=normal, 4=low
                status TEXT DEFAULT 'pending',  -- pending, in_progress, completed, cancelled
                due_date REAL,
                created_at REAL NOT NULL,
                completed_at REAL,
                parent_task_id INTEGER,  -- for subtasks
                recurrence TEXT,  -- JSON: {type: daily/weekly, interval: 1}
                related_memory_id INTEGER,
                tags TEXT,  -- JSON array
                FOREIGN KEY(parent_task_id) REFERENCES tasks(id),
                FOREIGN KEY(related_memory_id) REFERENCES memory_index(id)
            )
        ''')
        
        # 6. Memory Chains
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain_name TEXT,
                memory_ids TEXT NOT NULL,  -- JSON array of memory IDs in order
                created_at REAL NOT NULL
            )
        ''')
        
        # 7. Statistics and Analytics
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_stats (
                date TEXT PRIMARY KEY,  -- YYYY-MM-DD
                total_memories INTEGER DEFAULT 0,
                memories_created INTEGER DEFAULT 0,
                memories_accessed INTEGER DEFAULT 0,
                most_accessed_topic TEXT
            )
        ''')
        
        # Create indexes for fast querying
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_keywords 
            ON memory_index(keywords)
        ''')
        
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON memory_index(timestamp DESC)
        ''')
        
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_tags 
            ON memory_index(tags)
        ''')
        
        self.conn.commit()

    # =================================================================
    # Core Memory Operations
    # =================================================================
    
    def store_memory(
        self, 
        content: str, 
        title: str = None,
        memory_type: str = 'episodic',
        importance: int = 5,
        tags: List[str] = None,
        metadata: Dict = None
    ) -> int:
        """
        Save a new memory into the system
        
        Args:
            content: Full memory content
            title: Title of the memory (optional)
            memory_type: episodic/semantic/procedural
            importance: 1-10 (Significance scale)
            tags: List of tags
            metadata: Additional info dictionary
        
        Returns:
            memory_id
        """
        try:
            # Extract keywords
            keywords = self._extract_keywords(content)
            
            # Create a short summary
            summary = self._create_summary(content, max_length=200)
            
            # Autogenerate title if missing
            if not title:
                title = summary[:50] + "..." if len(summary) > 50 else summary
            
            # Calculate embedding (if available)
            embedding = None
            if self.embedding_model:
                embedding_vector = self.embedding_model.encode(content)
                embedding = embedding_vector.tobytes()
            
            timestamp = time.time()
            tags_json = json.dumps(tags or [])
            
            # Save into index
            self.cursor.execute('''
                INSERT INTO memory_index 
                (title, keywords, summary, memory_type, timestamp, last_accessed, 
                 importance_score, embedding, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, keywords, summary, memory_type, timestamp, timestamp,
                  float(importance), embedding, tags_json))
            
            memory_id = self.cursor.lastrowid
            
            # Save full details
            metadata_json = json.dumps(metadata or {})
            self.cursor.execute('''
                INSERT INTO memory_details 
                (memory_id, full_content, metadata, created_at)
                VALUES (?, ?, ?, ?)
            ''', (memory_id, content, metadata_json, timestamp))
            
            self.conn.commit()
            
            # Update stats
            self._update_stats('memory_created')
            
            print(f"   [Memory] 💾 Stored memory #{memory_id}: {title}")
            return memory_id
            
        except Exception as e:
            print(f"   [Memory] ❌ Error storing memory: {e}")
            return -1

    def recall_memory(
        self, 
        query: str, 
        limit: int = 5,
        memory_type: str = None,
        min_importance: float = 0.0,
        use_semantic: bool = True
    ) -> List[Dict]:
        """
        Retrieve memories related to a query
        
        Args:
            query: The search string
            limit: Number of results requested
            memory_type: Filter by memory type (optional)
            min_importance: Minimum importance threshold
            use_semantic: Toggle semantic search (embeddings)
        
        Returns:
            List of matched memories
        """
        try:
            memories = []
            
            # Semantic Search using embeddings
            if use_semantic and self.embedding_model:
                memories = self._semantic_search(query, limit, memory_type, min_importance)
            
            # Keyword Search (Fallback)
            if not memories:
                memories = self._keyword_search(query, limit, memory_type, min_importance)
            
            # Update last accessed and access count
            for memory in memories:
                self._update_access_stats(memory['id'])
            
            # Update overall stats
            self._update_stats('memory_accessed')
            
            return memories
            
        except Exception as e:
            print(f"   [Memory] ❌ Error recalling memory: {e}")
            return []

    def get_memory_details(self, memory_id: int) -> Optional[Dict]:
        """
        Fetch the full details of a specific memory
        """
        try:
            self.cursor.execute('''
                SELECT mi.*, md.full_content, md.metadata
                FROM memory_index mi
                JOIN memory_details md ON mi.id = md.memory_id
                WHERE mi.id = ?
            ''', (memory_id,))
            
            row = self.cursor.fetchone()
            if not row:
                return None
            
            # Update access stats
            self._update_access_stats(memory_id)
            
            return self._row_to_dict(row)
            
        except Exception as e:
            print(f"   [Memory] ❌ Error getting memory details: {e}")
            return None

    # =================================================================
    # Working Memory (Context Window)
    # =================================================================
    
    def add_to_working_memory(
        self, 
        content: str, 
        memory_type: str = 'conversation',
        expires_in_seconds: int = 3600,  # 1 hour default
        importance: int = 5,
        tags: List[str] = None
    ) -> int:
        """
        Add information to working memory (the current context)
        """
        try:
            timestamp = time.time()
            expires_at = timestamp + expires_in_seconds
            tags_json = json.dumps(tags or [])
            
            self.cursor.execute('''
                INSERT INTO working_memory 
                (content, memory_type, timestamp, expires_at, importance, tags)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (content, memory_type, timestamp, expires_at, importance, tags_json))
            
            self.conn.commit()
            return self.cursor.lastrowid
            
        except Exception as e:
            print(f"   [Memory] ❌ Error adding to working memory: {e}")
            return -1

    def get_working_memory(self, limit: int = 10) -> List[Dict]:
        """
        Fetch the current working memory (context)
        """
        try:
            current_time = time.time()
            
            # Delete expired memories
            self.cursor.execute('''
                DELETE FROM working_memory 
                WHERE expires_at < ?
            ''', (current_time,))
            
            # Fetch valid memories
            self.cursor.execute('''
                SELECT * FROM working_memory 
                WHERE expires_at > ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            ''', (current_time, limit))
            
            rows = self.cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"   [Memory] ❌ Error getting working memory: {e}")
            return []

    def clear_working_memory(self):
        """
        Wipe the working memory entirely
        """
        try:
            self.cursor.execute('DELETE FROM working_memory')
            self.conn.commit()
            print("   [Memory] 🗑️ Working memory cleared")
        except Exception as e:
            print(f"   [Memory] ❌ Error clearing working memory: {e}")

    # =================================================================
    # Knowledge Base (Semantic Memory)
    # =================================================================
    
    def store_knowledge(
        self, 
        entity: str, 
        entity_type: str,
        attributes: Dict,
        confidence: float = 1.0,
        source_memory_id: int = None
    ) -> int:
        try:
            # Check for an existing entity
            self.cursor.execute('''
                SELECT id, attributes FROM knowledge_base 
                WHERE entity = ? AND entity_type = ?
            ''', (entity, entity_type))
            
            existing = self.cursor.fetchone()
            timestamp = time.time()
            
            if existing:
                # Update existing
                existing_id, existing_attrs = existing
                existing_attrs_dict = json.loads(existing_attrs)
                existing_attrs_dict.update(attributes)  # Merge data
                
                self.cursor.execute('''
                    UPDATE knowledge_base 
                    SET attributes = ?, confidence = ?, updated_at = ?
                    WHERE id = ?
                ''', (json.dumps(existing_attrs_dict), confidence, timestamp, existing_id))
                
                entity_id = existing_id
                print(f"   [Memory] 🔄 Updated knowledge: {entity}")
            else:
                # Create new
                self.cursor.execute('''
                    INSERT INTO knowledge_base 
                    (entity, entity_type, attributes, confidence, source_memory_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (entity, entity_type, json.dumps(attributes), confidence, 
                      source_memory_id, timestamp))
                
                entity_id = self.cursor.lastrowid
                print(f"   [Memory] 💡 Stored knowledge: {entity}")
            
            # 🚀 Save knowledge as a text memory (Before returning and final commit)
            fact_content = f"Knowledge Base Fact -> Entity: {entity}, Type: {entity_type}. Details: {json.dumps(attributes, ensure_ascii=False)}"
            self.store_memory(
                content=fact_content,
                title=f"Fact: {entity}",
                memory_type='semantic',
                importance=8,
                tags=['knowledge_base', str(entity_type)]
            )
            
            self.conn.commit()
            return entity_id
            
        except Exception as e:
            print(f"   [Memory] ❌ Error storing knowledge: {e}")
            return -1

    def query_knowledge(self, entity: str = None, entity_type: str = None) -> List[Dict]:
        """
        Search the knowledge base
        """
        try:
            query = "SELECT * FROM knowledge_base WHERE 1=1"
            params = []
            
            if entity:
                query += " AND entity LIKE ?"
                params.append(f"%{entity}%")
            
            if entity_type:
                query += " AND entity_type = ?"
                params.append(entity_type)
            
            query += " ORDER BY confidence DESC, updated_at DESC"
            
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"   [Memory] ❌ Error querying knowledge: {e}")
            return []

    # =================================================================
    # TODO / Task System
    # =================================================================
    
    def create_task(
        self,
        title: str,
        description: str = None,
        priority: int = 3,
        due_date: datetime = None,
        tags: List[str] = None,
        parent_task_id: int = None,
        related_memory_id: int = None
    ) -> int:
        """
        Create a new task
        """
        try:
            timestamp = time.time()
            due_timestamp = due_date.timestamp() if due_date else None
            tags_json = json.dumps(tags or [])
            
            self.cursor.execute('''
                INSERT INTO tasks 
                (title, description, priority, due_date, created_at, 
                 parent_task_id, tags, related_memory_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, description, priority, due_timestamp, timestamp,
                  parent_task_id, tags_json, related_memory_id))
            
            task_id = self.cursor.lastrowid
            self.conn.commit()
            
            print(f"   [Memory] ✅ Task created #{task_id}: {title}")
            return task_id
            
        except Exception as e:
            print(f"   [Memory] ❌ Error creating task: {e}")
            return -1

    def get_tasks(
        self, 
        status: str = 'pending',
        priority_min: int = None,
        limit: int = None
    ) -> List[Dict]:
        """
        Fetch tasks based on parameters
        """
        try:
            query = "SELECT * FROM tasks WHERE status = ?"
            params = [status]
            
            if priority_min:
                query += " AND priority <= ?"
                params.append(priority_min)
            
            query += " ORDER BY priority ASC, due_date ASC"
            
            if limit:
                query += f" LIMIT {limit}"
            
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"   [Memory] ❌ Error getting tasks: {e}")
            return []

    def complete_task(self, task_id: int) -> bool:
        """
        Mark a task as completed
        """
        try:
            self.cursor.execute('''
                UPDATE tasks 
                SET status = 'completed', completed_at = ?
                WHERE id = ?
            ''', (time.time(), task_id))
            
            self.conn.commit()
            print(f"   [Memory] ✅ Task #{task_id} marked as completed")
            return True
            
        except Exception as e:
            print(f"   [Memory] ❌ Error completing task: {e}")
            return False

    # =================================================================
    # Helper Methods
    # =================================================================
    
    def _extract_keywords(self, text: str, max_keywords: int = 10) -> str:
        """
        Extract keywords from text
        (Basic version - can be upgraded via NLP)
        """
        # Remove basic stop words
        stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by'}
        
        # Extract words
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter and rank by frequency
        word_freq = {}
        for word in words:
            if word not in stop_words and len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Take the most frequent words
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [word for word, _ in sorted_words[:max_keywords]]
        
        return ' '.join(keywords)

    def _create_summary(self, text: str, max_length: int = 200) -> str:
        """
        Create a short text summary
        """
        # Basic version: take the first sentences up to max_length
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

    def _semantic_search(
        self, 
        query: str, 
        limit: int,
        memory_type: str,
        min_importance: float
    ) -> List[Dict]:
        """
        Perform semantic search utilizing embeddings
        """
        try:
            if not self.embedding_model:
                return []
            
            # Calculate query embedding
            query_embedding = self.embedding_model.encode(query)
            
            # Fetch all memories containing embeddings
            sql = """
                SELECT mi.*, md.full_content, md.metadata 
                FROM memory_index mi 
                LEFT JOIN memory_details md ON mi.id = md.memory_id 
                WHERE mi.embedding IS NOT NULL
            """
            params = []
            
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            
            if min_importance > 0:
                sql += " AND importance_score >= ?"
                params.append(min_importance)
            
            self.cursor.execute(sql, params)
            rows = self.cursor.fetchall()
            
            # Compute cosine similarity
            similarities = []
            for row in rows:
                embedding_bytes = row[9]  # embedding column
                if embedding_bytes:
                    memory_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
                    similarity = np.dot(query_embedding, memory_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(memory_embedding)
                    )
                    similarities.append((row, similarity))
            
            # Sort by similarity
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Return top results
            results = []
            for row, similarity in similarities[:limit]:
                memory_dict = self._row_to_dict(row)
                memory_dict['similarity_score'] = float(similarity)
                results.append(memory_dict)
            
            return results
            
        except Exception as e:
            print(f"   [Memory] ❌ Semantic search error: {e}")
            return []

    def _keyword_search(
        self, 
        query: str, 
        limit: int,
        memory_type: str,
        min_importance: float
    ) -> List[Dict]:
        """
        Enhanced keyword search (supports separated words to bypass STT misinterpretations)
        """
        try:
            # 1. Clean the user's query of stop words
            stop_words = {'what', 'is', 'the', 'project', 'tell', 'me', 'about', 'who', 'how', 'a', 'an', 'in', 'on', 'at', 'do', 'i', 'prefer', 'using'}
            words = [w for w in re.findall(r'\b\w+\b', query.lower()) if w not in stop_words and len(w) > 2]
            
            # If the user said one word or no useful words were extracted, use the whole phrase as a fallback
            if not words:
                words = [query.lower().strip()]
                
            # 🚀 Merge details to access full_content
            sql = """
                SELECT mi.*, md.full_content, md.metadata 
                FROM memory_index mi 
                LEFT JOIN memory_details md ON mi.id = md.memory_id 
                WHERE 
            """
            conditions = []
            params = []
            
            for word in words:
                conditions.append("(mi.keywords LIKE ? OR mi.title LIKE ? OR mi.summary LIKE ? OR md.full_content LIKE ?)")
                params.extend([f"%{word}%", f"%{word}%", f"%{word}%", f"%{word}%"])
                
            sql += "(" + " OR ".join(conditions) + ")"
            
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            
            if min_importance > 0:
                sql += " AND importance_score >= ?"
                params.append(min_importance)
            
            sql += " ORDER BY importance_score DESC, timestamp DESC LIMIT ?"
            params.append(limit)
            
            self.cursor.execute(sql, params)
            rows = self.cursor.fetchall()
            
            return [self._row_to_dict(row) for row in rows]
            
        except Exception as e:
            print(f"   [Memory] ❌ Keyword search error: {e}")
            return []
    
    def _update_access_stats(self, memory_id: int):
        """
        Update memory access statistics
        """
        try:
            self.cursor.execute('''
                UPDATE memory_index 
                SET last_accessed = ?, access_count = access_count + 1
                WHERE id = ?
            ''', (time.time(), memory_id))
            self.conn.commit()
        except Exception:
            pass

    def _update_stats(self, stat_type: str):
        """
        Update daily system statistics
        """
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Ensure a record exists for today
            self.cursor.execute('''
                INSERT OR IGNORE INTO memory_stats (date) VALUES (?)
            ''', (today,))
            
            # Update based on the trigger type
            if stat_type == 'memory_created':
                self.cursor.execute('''
                    UPDATE memory_stats 
                    SET total_memories = total_memories + 1,
                        memories_created = memories_created + 1
                    WHERE date = ?
                ''', (today,))
            elif stat_type == 'memory_accessed':
                self.cursor.execute('''
                    UPDATE memory_stats 
                    SET memories_accessed = memories_accessed + 1
                    WHERE date = ?
                ''', (today,))
            
            self.conn.commit()
        except Exception:
            pass

    def _row_to_dict(self, row) -> Dict:
        """
        Convert a database row into a dictionary
        """
        if not row:
            return {}
        
        columns = [desc[0] for desc in self.cursor.description]
        result = dict(zip(columns, row))
        
        # Parse JSON strings into objects
        for key in ['tags', 'metadata', 'attributes', 'related_memories']:
            if key in result and result[key]:
                try:
                    result[key] = json.loads(result[key])
                except:
                    pass
        
        return result

    def __del__(self):
        """
        Safely close the database connection upon destruction
        """
        try:
            self.conn.close()
        except:
            pass


# =================================================================
# System Testing (Generic Open-Source Data)
# =================================================================
if __name__ == "__main__":
    print("="*60)
    print("   🧠 JARVIS Memory System Test")
    print("="*60)
    
    memory = MemoryManager()
    
    # 1. Storing Episodic Memories
    print("\n1️⃣ Storing episodic memories...")
    memory.store_memory(
        content="On setup day, the user successfully cloned JARVIS-NEXUS from VANT-HQ and configured the local Ollama LLM environment.",
        title="JARVIS Initial Setup",
        memory_type='episodic',
        importance=9,
        tags=['project', 'jarvis', 'setup', 'github']
    )
    
    memory.store_memory(
        content="The user mentioned preferring dark mode across all IDEs and uses VS Code as their primary editor.",
        title="User IDE Preferences",
        memory_type='episodic',
        importance=4,
        tags=['preferences', 'ide', 'vscode']
    )

    # 2. Semantic Memory / Knowledge Base
    print("\n2️⃣ Storing knowledge base facts...")
    memory.store_knowledge(
        entity="User",
        entity_type="person",
        attributes={
            "role": "Lead Developer",
            "company": "Open Source Contributor",
            "key_interests": ["AI", "Automation", "Python"],
            "current_main_project": "JARVIS Nexus Customization"
        }
    )

    memory.store_knowledge(
        entity="JARVIS Nexus",
        entity_type="project",
        attributes={
            "description": "An open-source, fully offline, local AI assistant ecosystem.",
            "repository": "https://github.com/VANT-HQ/JARVIS-NEXUS",
            "status": "Active Development"
        }
    )
    
    # 3. Procedural Memory / Tasks
    print("\n3️⃣ Creating tasks...")
    memory.create_task(
        title="Install required Python dependencies",
        description="Run pip install -r requirements.txt to ensure all audio and AI packages are available.",
        priority=1,
        tags=['setup', 'dependencies']
    )

    memory.create_task(
        title="Configure local LLM API",
        description="Verify that Ollama is running on localhost:11434 and the correct model is pulled.",
        priority=2,
        tags=['llm', 'configuration']
    )
    
    # 4. Testing Recall
    print("\n4️⃣ Recalling memories (Test: 'JARVIS Nexus repository')...")
    memories = memory.recall_memory("JARVIS Nexus repository", limit=3)
    for mem in memories:
        print(f"   - {mem.get('title', 'Untitled')} (Score: {mem.get('similarity_score', 0):.2f})")
    
    # 5. Getting Tasks
    print("\n5️⃣ Getting tasks...")
    tasks = memory.get_tasks(status='pending')
    for task in tasks:
        print(f"   - [Priority {task['priority']}] {task['title']}")
    
    # 6. Querying Knowledge
    print("\n6️⃣ Querying knowledge (Entity: User)...")
    knowledge = memory.query_knowledge(entity="User")
    for k in knowledge:
        print(f"   - {k['entity']} ({k['entity_type']}): {k['attributes']}")
    
    print("\n✅ Memory system test complete! Database is primed.")