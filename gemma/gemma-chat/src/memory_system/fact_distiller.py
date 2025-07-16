"""Fact distillation from conversations and events"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Set
import re
from dataclasses import dataclass

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

@dataclass
class Fact:
    """Represents a distilled fact"""
    content: str
    confidence: float
    timestamp: float
    source: str
    category: str = "general"
    importance: float = 0.5
    related_facts: List[str] = None
    
    def __post_init__(self):
        if self.related_facts is None:
            self.related_facts = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'content': self.content,
            'confidence': self.confidence,
            'timestamp': self.timestamp,
            'source': self.source,
            'category': self.category,
            'importance': self.importance,
            'related_facts': self.related_facts
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Fact":
        return cls(**data)

class FactDistiller:
    """Distills facts from conversations and events using AI model"""
    
    def __init__(self, model_name: str = "microsoft/DialoGPT-medium", cache_dir: str = "./models"):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.logger = logging.getLogger(__name__)
        
        # Model components
        self.tokenizer = None
        self.model = None
        self.distillation_pipeline = None
        
        # Fact extraction patterns
        self.fact_patterns = [
            r"My name is (\w+)",
            r"I am (\d+) years old",
            r"I live in ([^.]+)",
            r"I work as a ([^.]+)",
            r"I like ([^.]+)",
            r"I don't like ([^.]+)",
            r"I can ([^.]+)",
            r"I cannot ([^.]+)",
            r"The user is ([^.]+)",
            r"The user has ([^.]+)",
            r"The user wants ([^.]+)",
            r"The user said ([^.]+)",
        ]
        
        # Category mappings
        self.category_keywords = {
            'personal': ['name', 'age', 'live', 'work', 'family'],
            'preferences': ['like', 'prefer', 'favorite', 'enjoy', 'hate', 'dislike'],
            'abilities': ['can', 'cannot', 'able', 'unable', 'skill', 'talent'],
            'objects': ['object', 'thing', 'item', 'detected', 'visible', 'seen'],
            'actions': ['action', 'doing', 'performed', 'executed', 'completed'],
            'temporal': ['when', 'time', 'date', 'yesterday', 'today', 'tomorrow'],
            'spatial': ['where', 'location', 'place', 'here', 'there', 'room']
        }
        
        # Initialize model
        self._initialize_model()
        
        # Statistics
        self.distilled_facts = 0
        self.processing_times = []
    
    def _initialize_model(self):
        """Initialize the fact distillation model"""
        try:
            if not TRANSFORMERS_AVAILABLE:
                self.logger.warning("Transformers not available, using pattern-based distillation")
                return
            
            # Load tokenizer and model for fact distillation
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir
            )
            
            # For now, use a simple text generation model
            # In production, this would be a specialized fact extraction model
            self.distillation_pipeline = pipeline(
                "text-generation",
                model=self.model_name,
                tokenizer=self.tokenizer,
                max_length=100,
                cache_dir=self.cache_dir
            )
            
            self.logger.info(f"Fact distillation model loaded: {self.model_name}")
            
        except Exception as e:
            self.logger.error(f"Error loading distillation model: {e}")
            self.distillation_pipeline = None
    
    async def distill_facts_from_conversation(self, 
                                            user_input: str, 
                                            assistant_response: str,
                                            context: Optional[Dict[str, Any]] = None) -> List[Fact]:
        """Distill facts from a conversation exchange"""
        start_time = time.time()
        
        try:
            facts = []
            
            # Extract facts from user input
            user_facts = await self._extract_facts_from_text(
                user_input, 
                source="user_input",
                context=context
            )
            facts.extend(user_facts)
            
            # Extract facts from assistant response
            response_facts = await self._extract_facts_from_text(
                assistant_response,
                source="assistant_response", 
                context=context
            )
            facts.extend(response_facts)
            
            # Extract contextual facts
            if context:
                context_facts = await self._extract_contextual_facts(context)
                facts.extend(context_facts)
            
            # Update statistics
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            self.distilled_facts += len(facts)
            
            if len(self.processing_times) > 100:
                self.processing_times.pop(0)
            
            self.logger.debug(f"Distilled {len(facts)} facts in {processing_time:.2f}s")
            
            return facts
            
        except Exception as e:
            self.logger.error(f"Error distilling facts: {e}")
            return []
    
    async def _extract_facts_from_text(self, 
                                     text: str, 
                                     source: str,
                                     context: Optional[Dict[str, Any]] = None) -> List[Fact]:
        """Extract facts from text using patterns and AI"""
        facts = []
        
        if not text or not text.strip():
            return facts
        
        # Pattern-based extraction
        pattern_facts = self._extract_with_patterns(text, source)
        facts.extend(pattern_facts)
        
        # AI-based extraction
        if self.distillation_pipeline:
            ai_facts = await self._extract_with_ai(text, source, context)
            facts.extend(ai_facts)
        
        return facts
    
    def _extract_with_patterns(self, text: str, source: str) -> List[Fact]:
        """Extract facts using regex patterns"""
        facts = []
        text_lower = text.lower()
        
        for pattern in self.fact_patterns:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                fact_content = match.group(0)
                confidence = 0.8  # High confidence for pattern matches
                category = self._categorize_fact(fact_content)
                importance = self._calculate_importance(fact_content, category)
                
                fact = Fact(
                    content=fact_content,
                    confidence=confidence,
                    timestamp=time.time(),
                    source=source,
                    category=category,
                    importance=importance
                )
                facts.append(fact)
        
        return facts
    
    async def _extract_with_ai(self, 
                             text: str, 
                             source: str,
                             context: Optional[Dict[str, Any]] = None) -> List[Fact]:
        """Extract facts using AI model"""
        try:
            # Create a prompt for fact extraction
            prompt = self._create_fact_extraction_prompt(text, context)
            
            # Generate fact extraction
            result = self.distillation_pipeline(
                prompt,
                max_length=len(prompt.split()) + 50,
                num_return_sequences=1,
                temperature=0.3,
                do_sample=True
            )
            
            if result and len(result) > 0:
                generated_text = result[0]['generated_text']
                
                # Parse extracted facts
                facts = self._parse_generated_facts(generated_text, source)
                return facts
            
        except Exception as e:
            self.logger.error(f"Error in AI fact extraction: {e}")
        
        return []
    
    def _create_fact_extraction_prompt(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Create prompt for AI fact extraction"""
        prompt = f"""Extract important facts from this text:
Text: "{text}"

Important facts:
1."""
        
        if context and context.get('wake_word_active'):
            prompt += "\nNote: This was said after a wake word, indicating direct communication."
        
        return prompt
    
    def _parse_generated_facts(self, generated_text: str, source: str) -> List[Fact]:
        """Parse facts from AI-generated text"""
        facts = []
        
        # Simple parsing - look for numbered list items
        lines = generated_text.split('\n')
        for line in lines:
            line = line.strip()
            if re.match(r'^\d+\.', line):
                fact_content = re.sub(r'^\d+\.\s*', '', line).strip()
                if fact_content and len(fact_content) > 5:  # Filter very short facts
                    category = self._categorize_fact(fact_content)
                    importance = self._calculate_importance(fact_content, category)
                    
                    fact = Fact(
                        content=fact_content,
                        confidence=0.6,  # Lower confidence for AI extraction
                        timestamp=time.time(),
                        source=source,
                        category=category,
                        importance=importance
                    )
                    facts.append(fact)
        
        return facts
    
    async def _extract_contextual_facts(self, context: Dict[str, Any]) -> List[Fact]:
        """Extract facts from context information"""
        facts = []
        
        try:
            # Object detection facts
            if 'detections' in context:
                for detection in context['detections']:
                    fact_content = f"Detected {detection.get('class_name')} with {detection.get('confidence', 0):.2f} confidence"
                    fact = Fact(
                        content=fact_content,
                        confidence=detection.get('confidence', 0.5),
                        timestamp=time.time(),
                        source="camera_detection",
                        category="objects",
                        importance=0.3
                    )
                    facts.append(fact)
            
            # Wake word facts
            if context.get('wake_word_active'):
                wake_word = context.get('wake_word', 'unknown')
                fact_content = f"User activated with wake word: {wake_word}"
                fact = Fact(
                    content=fact_content,
                    confidence=0.9,
                    timestamp=time.time(),
                    source="wake_word_detection",
                    category="temporal",
                    importance=0.6
                )
                facts.append(fact)
            
            # Speech activity facts
            if context.get('speech_active'):
                fact_content = "User is currently speaking"
                fact = Fact(
                    content=fact_content,
                    confidence=context.get('speech_confidence', 0.7),
                    timestamp=time.time(),
                    source="speech_detection",
                    category="temporal",
                    importance=0.4
                )
                facts.append(fact)
                
        except Exception as e:
            self.logger.error(f"Error extracting contextual facts: {e}")
        
        return facts
    
    def _categorize_fact(self, fact_content: str) -> str:
        """Categorize a fact based on keywords"""
        fact_lower = fact_content.lower()
        
        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                if keyword in fact_lower:
                    return category
        
        return "general"
    
    def _calculate_importance(self, fact_content: str, category: str) -> float:
        """Calculate importance score for a fact"""
        base_importance = {
            'personal': 0.9,
            'preferences': 0.7,
            'abilities': 0.8,
            'objects': 0.3,
            'actions': 0.5,
            'temporal': 0.6,
            'spatial': 0.6,
            'general': 0.5
        }.get(category, 0.5)
        
        # Adjust based on content length and specificity
        length_factor = min(len(fact_content) / 50, 1.0)  # Longer facts may be more important
        specificity_factor = 1.0
        
        # Check for specific indicators
        fact_lower = fact_content.lower()
        if any(word in fact_lower for word in ['name', 'age', 'address']):
            specificity_factor = 1.2
        elif any(word in fact_lower for word in ['like', 'love', 'hate']):
            specificity_factor = 1.1
        
        importance = base_importance * length_factor * specificity_factor
        return min(importance, 1.0)  # Cap at 1.0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get distillation statistics"""
        avg_processing_time = (sum(self.processing_times) / len(self.processing_times) 
                             if self.processing_times else 0)
        
        return {
            'model_loaded': self.distillation_pipeline is not None,
            'distilled_facts': self.distilled_facts,
            'avg_processing_time': avg_processing_time,
            'supported_categories': list(self.category_keywords.keys()),
            'pattern_count': len(self.fact_patterns)
        }