from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Any, Optional, Union

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='allow')
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra='allow')
    
    messages: List[ChatMessage] = Field(..., max_length=100)
    stream: Optional[bool] = False
    preset: Optional[str] = None
    model: Optional[str] = None
