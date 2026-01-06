from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

load_dotenv()
OllamaModel = os.getenv('OllamaModel')

template = """Question: {question}

Answer: Let's make as short and simple as possible."""

question = input('what is your question? ')

prompt = ChatPromptTemplate.from_template(template)

model = OllamaLLM(model=OllamaModel)

chain = prompt | model

ans = chain.invoke({'question': {question}})
print(ans)
