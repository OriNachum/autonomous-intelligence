"""Immediate memory system for short-term fact storage and retrieval"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import heapq
from dataclasses import asdict

from .fact_distiller import Fact, FactDistiller

class ImmediateMemory:
    """Manages immediate memory with fact storage and retrieval"""
    
    def __init__(self, max_facts: int = 100, relevance_threshold: float = 0.3):
        self.max_facts = max_facts
        self.relevance_threshold = relevance_threshold
        self.logger = logging.getLogger(__name__)
        
        # Fact storage
        self.facts: List[Fact] = []
        self.facts_by_category: Dict[str, List[Fact]] = defaultdict(list)
        self.facts_by_source: Dict[str, List[Fact]] = defaultdict(list)
        
        # Fact index for quick lookup
        self.fact_index: Dict[str, Set[int]] = defaultdict(set)  # keyword -> fact indices
        
        # Access tracking for importance scoring
        self.fact_access_count: Dict[int, int] = defaultdict(int)
        self.last_access_time: Dict[int, float] = {}
        
        # Memory statistics
        self.total_facts_added = 0
        self.total_facts_archived = 0
        self.retrieval_count = 0
        self.archival_decisions = 0
        
        # Archival history
        self.archived_facts: List[Fact] = []
        self.max_archived = 500
    
    async def add_fact(self, fact: Fact) -> bool:
        """Add a fact to immediate memory"""
        try:
            # Check for duplicates
            if self._is_duplicate(fact):
                self.logger.debug(f"Skipping duplicate fact: {fact.content}")
                return False
            
            # Add to main storage
            fact_index = len(self.facts)
            self.facts.append(fact)
            
            # Add to category index
            self.facts_by_category[fact.category].append(fact)
            
            # Add to source index
            self.facts_by_source[fact.source].append(fact)
            
            # Update keyword index
            self._update_fact_index(fact, fact_index)
            
            # Initialize access tracking
            self.fact_access_count[fact_index] = 0
            self.last_access_time[fact_index] = time.time()
            
            self.total_facts_added += 1
            
            # Check if we need to archive old facts
            if len(self.facts) > self.max_facts:
                await self._archive_old_facts()
            
            self.logger.debug(f"Added fact: {fact.content[:50]}...")
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding fact: {e}")
            return False
    
    async def add_facts(self, facts: List[Fact]) -> int:
        """Add multiple facts to memory"""
        added_count = 0
        for fact in facts:
            if await self.add_fact(fact):
                added_count += 1
        return added_count
    
    async def retrieve_relevant_facts(self, 
                                    query: str, 
                                    context: Optional[Dict[str, Any]] = None,
                                    max_facts: int = 10) -> List[Fact]:
        """Retrieve facts relevant to a query"""
        try:
            self.retrieval_count += 1
            
            # Calculate relevance scores for all facts
            scored_facts = []
            query_lower = query.lower()
            
            for i, fact in enumerate(self.facts):
                relevance_score = self._calculate_relevance(fact, query_lower, context, i)
                
                if relevance_score >= self.relevance_threshold:
                    scored_facts.append((relevance_score, i, fact))
            
            # Sort by relevance score (descending)
            scored_facts.sort(key=lambda x: x[0], reverse=True)
            
            # Update access tracking
            relevant_facts = []
            for score, fact_index, fact in scored_facts[:max_facts]:
                self.fact_access_count[fact_index] += 1
                self.last_access_time[fact_index] = time.time()
                relevant_facts.append(fact)
            
            self.logger.debug(f"Retrieved {len(relevant_facts)} relevant facts for query: {query[:30]}...")
            return relevant_facts
            
        except Exception as e:
            self.logger.error(f"Error retrieving facts: {e}")
            return []
    
    def _calculate_relevance(self, 
                           fact: Fact, 
                           query_lower: str,
                           context: Optional[Dict[str, Any]],
                           fact_index: int) -> float:
        """Calculate relevance score for a fact"""
        score = 0.0
        fact_content_lower = fact.content.lower()
        
        # Keyword matching
        query_words = set(query_lower.split())
        fact_words = set(fact_content_lower.split())
        
        # Exact word matches
        word_matches = len(query_words.intersection(fact_words))
        if word_matches > 0:
            score += word_matches * 0.3
        
        # Partial word matches
        for query_word in query_words:
            for fact_word in fact_words:
                if query_word in fact_word or fact_word in query_word:
                    score += 0.1
        
        # Boost based on fact importance
        score += fact.importance * 0.2
        
        # Boost based on fact confidence
        score += fact.confidence * 0.1
        
        # Boost recent facts
        age_hours = (time.time() - fact.timestamp) / 3600
        if age_hours < 1:
            score += 0.2
        elif age_hours < 24:
            score += 0.1
        
        # Boost frequently accessed facts
        access_boost = min(self.fact_access_count[fact_index] * 0.05, 0.2)
        score += access_boost
        
        # Context-based boosting
        if context:
            # Boost facts from same source
            if fact.source == context.get('last_source'):
                score += 0.1
            
            # Boost facts from same category as recent activity
            if fact.category == context.get('active_category'):
                score += 0.1
            
            # Boost object-related facts if objects are detected
            if context.get('detections') and fact.category == 'objects':
                score += 0.15
        
        return score
    
    def _is_duplicate(self, new_fact: Fact) -> bool:
        """Check if a fact is a duplicate"""
        new_content_lower = new_fact.content.lower()
        
        for existing_fact in self.facts:
            existing_content_lower = existing_fact.content.lower()
            
            # Exact match
            if new_content_lower == existing_content_lower:
                return True
            
            # High similarity (simple check)
            if self._similarity_score(new_content_lower, existing_content_lower) > 0.8:
                return True
        
        return False
    
    def _similarity_score(self, text1: str, text2: str) -> float:
        """Calculate simple similarity score between two texts"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _update_fact_index(self, fact: Fact, fact_index: int):
        """Update keyword index for fast fact lookup"""
        words = fact.content.lower().split()
        for word in words:
            # Remove punctuation
            word = ''.join(c for c in word if c.isalnum())
            if len(word) > 2:  # Only index words longer than 2 characters
                self.fact_index[word].add(fact_index)
    
    async def _archive_old_facts(self):
        """Archive old facts to make room for new ones"""
        try:
            # Calculate archival scores for all facts
            archival_candidates = []
            
            for i, fact in enumerate(self.facts):
                archival_score = self._calculate_archival_score(fact, i)
                archival_candidates.append((archival_score, i, fact))
            
            # Sort by archival score (ascending - lower scores get archived first)
            archival_candidates.sort(key=lambda x: x[0])
            
            # Archive facts until we're under the limit
            facts_to_archive = len(self.facts) - self.max_facts + 10  # Archive a few extra
            
            archived_indices = set()
            for i in range(min(facts_to_archive, len(archival_candidates))):
                score, fact_index, fact = archival_candidates[i]
                self.archived_facts.append(fact)
                archived_indices.add(fact_index)
                self.total_facts_archived += 1
            
            # Remove archived facts from active memory
            self._remove_facts_by_indices(archived_indices)
            
            # Trim archived facts if too many
            if len(self.archived_facts) > self.max_archived:
                self.archived_facts = self.archived_facts[-self.max_archived:]
            
            self.archival_decisions += 1
            self.logger.info(f"Archived {len(archived_indices)} facts")
            
        except Exception as e:
            self.logger.error(f"Error archiving facts: {e}")
    
    def _calculate_archival_score(self, fact: Fact, fact_index: int) -> float:
        """Calculate score for archival decision (lower = more likely to archive)"""
        score = 0.0
        
        # Age factor (older facts more likely to be archived)
        age_hours = (time.time() - fact.timestamp) / 3600
        score -= age_hours * 0.1
        
        # Importance factor (important facts less likely to be archived)
        score += fact.importance * 100
        
        # Access frequency factor
        score += self.fact_access_count[fact_index] * 10
        
        # Recent access factor
        if fact_index in self.last_access_time:
            hours_since_access = (time.time() - self.last_access_time[fact_index]) / 3600
            score -= hours_since_access * 0.05
        
        # Category factor (some categories more important)
        category_weights = {
            'personal': 1.0,
            'preferences': 0.8,
            'abilities': 0.9,
            'objects': 0.3,
            'actions': 0.4,
            'temporal': 0.5,
            'spatial': 0.6,
            'general': 0.5
        }
        score += category_weights.get(fact.category, 0.5) * 50
        
        return score
    
    def _remove_facts_by_indices(self, indices_to_remove: Set[int]):
        """Remove facts by their indices and update all data structures"""
        # Create mapping of old indices to new indices
        index_mapping = {}
        new_facts = []
        
        for old_index, fact in enumerate(self.facts):
            if old_index not in indices_to_remove:
                new_index = len(new_facts)
                index_mapping[old_index] = new_index
                new_facts.append(fact)
        
        # Update main facts list
        self.facts = new_facts
        
        # Rebuild category and source indices
        self.facts_by_category = defaultdict(list)
        self.facts_by_source = defaultdict(list)
        
        for fact in self.facts:
            self.facts_by_category[fact.category].append(fact)
            self.facts_by_source[fact.source].append(fact)
        
        # Rebuild keyword index
        self.fact_index = defaultdict(set)
        for new_index, fact in enumerate(self.facts):
            self._update_fact_index(fact, new_index)
        
        # Update access tracking with new indices
        new_access_count = defaultdict(int)
        new_last_access = {}
        
        for old_index, new_index in index_mapping.items():
            if old_index in self.fact_access_count:
                new_access_count[new_index] = self.fact_access_count[old_index]
            if old_index in self.last_access_time:
                new_last_access[new_index] = self.last_access_time[old_index]
        
        self.fact_access_count = new_access_count
        self.last_access_time = new_last_access
    
    def get_facts_by_category(self, category: str) -> List[Fact]:
        """Get all facts from a specific category"""
        return self.facts_by_category[category].copy()
    
    def get_facts_by_source(self, source: str) -> List[Fact]:
        """Get all facts from a specific source"""
        return self.facts_by_source[source].copy()
    
    def get_recent_facts(self, hours: float = 1.0) -> List[Fact]:
        """Get facts from the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        return [fact for fact in self.facts if fact.timestamp >= cutoff_time]
    
    def get_important_facts(self, min_importance: float = 0.7) -> List[Fact]:
        """Get facts above a certain importance threshold"""
        return [fact for fact in self.facts if fact.importance >= min_importance]
    
    def clear_memory(self):
        """Clear all facts from memory"""
        self.facts = []
        self.facts_by_category = defaultdict(list)
        self.facts_by_source = defaultdict(list)
        self.fact_index = defaultdict(set)
        self.fact_access_count = defaultdict(int)
        self.last_access_time = {}
        self.logger.info("Cleared immediate memory")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics"""
        category_counts = {cat: len(facts) for cat, facts in self.facts_by_category.items()}
        source_counts = {src: len(facts) for src, facts in self.facts_by_source.items()}
        
        return {
            'total_facts': len(self.facts),
            'max_facts': self.max_facts,
            'facts_by_category': category_counts,
            'facts_by_source': source_counts,
            'total_facts_added': self.total_facts_added,
            'total_facts_archived': self.total_facts_archived,
            'archived_facts_count': len(self.archived_facts),
            'retrieval_count': self.retrieval_count,
            'archival_decisions': self.archival_decisions,
            'memory_utilization': len(self.facts) / self.max_facts,
            'keyword_index_size': len(self.fact_index)
        }
    
    def export_facts(self) -> List[Dict[str, Any]]:
        """Export all facts as dictionaries"""
        return [fact.to_dict() for fact in self.facts]
    
    def import_facts(self, fact_dicts: List[Dict[str, Any]]) -> int:
        """Import facts from dictionaries"""
        imported_count = 0
        for fact_dict in fact_dicts:
            try:
                fact = Fact.from_dict(fact_dict)
                if asyncio.run(self.add_fact(fact)):
                    imported_count += 1
            except Exception as e:
                self.logger.error(f"Error importing fact: {e}")
        
        return imported_count