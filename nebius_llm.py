# nebius_llm.py
import os
from openai import OpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from typing import Any, Dict, List, Optional

class ChatNebius(BaseChatModel):
    model_name: str
    nebius_api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 0.95
    client: Any = None   
    
    def __init__(
        self,
        model: str,
        nebius_api_key: Optional[str] = None,
        temperature: float = 0.7, 
        max_tokens: int = 512,
        top_p: float = 0.95,
        **kwargs
    ):
        super().__init__(
            model_name=model, 
            nebius_api_key=nebius_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            **kwargs
        )
        # Initialize the client here
        self.client = OpenAI(
            base_url="https://api.studio.nebius.com/v1/",
            api_key=self.nebius_api_key or os.environ.get("NEBIUS_API_KEY")
        )
    
    @property
    def _llm_type(self) -> str:
        return "nebius"
    
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager: Optional[Any] = None, **kwargs) -> ChatResult:
        message_dicts = []
        for message in messages:
            if isinstance(message, SystemMessage):
                message_dicts.append({"role": "system", "content": message.content})
            elif isinstance(message, HumanMessage):
                message_dicts.append({"role": "user", "content": message.content})
            elif isinstance(message, AIMessage):
                message_dicts.append({"role": "assistant", "content": message.content})
            else:
                message_dicts.append({"role": "user", "content": str(message.content)})
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            messages=message_dicts,
            **kwargs
        )
        
        ai_message = AIMessage(content=response.choices[0].message.content)
        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])
        
    def invoke(self, messages: List[BaseMessage], **kwargs) -> AIMessage:
        result = self._generate(messages, **kwargs)
        return result.generations[0].message