from langsmith import traceable
import json
import operator
from dataclasses import dataclass, field
from typing_extensions import TypedDict, Annotated, Literal
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from langchain_core.messages import HumanMessage, SystemMessage 
from langchain_groq import ChatGroq
from tavily import TavilyClient
import os
from configuration import Configuration  

import time
start_time = time.time()

from dotenv import load_dotenv
load_dotenv()

def deduplicate_and_format_sources(search_response, max_tokens_per_source, include_raw_content=True):
    """
    Takes either a single search response or list of responses from Tavily API and formats them.
    Limits the raw_content to approximately max_tokens_per_source.
    include_raw_content specifies whether to include the raw_content from Tavily in the formatted string.
    
    Args:
        search_response: Either:
            - A dict with a 'results' key containing a list of search results
            - A list of dicts, each containing search results
            
    Returns:
        str: Formatted string with deduplicated sources
    """ 
    if isinstance(search_response, dict):
        sources_list = search_response['results']
    elif isinstance(search_response, list):
        sources_list = []
        for response in search_response:
            if isinstance(response, dict) and 'results' in response:
                sources_list.extend(response['results'])
            else:
                sources_list.extend(response)
    else:
        raise ValueError("Input must be either a dict with 'results' or a list of search results")
     
    unique_sources = {}
    for source in sources_list:
        if source['url'] not in unique_sources:
            unique_sources[source['url']] = source
     
    formatted_text = "Sources:\n\n"
    for i, source in enumerate(unique_sources.values(), 1):
        formatted_text += f"Source {source['title']}:\n===\n"
        formatted_text += f"URL: {source['url']}\n===\n"
        formatted_text += f"Most relevant content from source: {source['content']}\n===\n"
        if include_raw_content: 
            char_limit = max_tokens_per_source * 4 
            raw_content = source.get('raw_content', '')
            if raw_content is None:
                raw_content = ''
                print(f"Warning: No raw_content found for source {source['url']}")
            if len(raw_content) > char_limit:
                raw_content = raw_content[:char_limit] + "... [truncated]"
            formatted_text += f"Full source content limited to {max_tokens_per_source} tokens: {raw_content}\n\n"
                
    return formatted_text.strip()

def format_sources(search_results):
    """Format search results into a bullet-point list of sources.
    
    Args:
        search_results (dict): Tavily search response containing results
        
    Returns:
        str: Formatted string with sources and their URLs
    """
    return '\n'.join(
        f"* {source['title']} : {source['url']}"
        for source in search_results['results']
    )
 
@traceable
def tavily_search(query, include_raw_content=True, max_results=3):
    """ Search the web using the Tavily API.
    
    Args:
        query (str): The search query to execute
        include_raw_content (bool): Whether to include the raw_content from Tavily in the formatted string
        max_results (int): Maximum number of results to return
        
    Returns:
        dict: Tavily search response containing:
            - results (list): List of search result dictionaries, each containing:
                - title (str): Title of the search result
                - url (str): URL of the search result
                - content (str): Snippet/summary of the content
                - raw_content (str): Full content of the page if available
    """
    try:
        TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
        if not TAVILY_API_KEY:  
            print("Warning: Using hardcoded API key. Set TAVILY_API_KEY environment variable.")
            
        tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        return tavily_client.search(query, max_results=max_results, include_raw_content=include_raw_content)
    except Exception as e:
        print(f"Error in Tavily search: {e}") 
        return {"results": []}


GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
local_llm = "mistral-saba-24b" 

llm = ChatGroq(model=local_llm, temperature=0, groq_api_key=GROQ_API_KEY)
llm_json_mode = ChatGroq(model=local_llm, temperature=0, groq_api_key=GROQ_API_KEY, model_kwargs={"response_format": {"type": "json_object"}})

@dataclass(kw_only=True)
class SummaryState:
    research_topic: str = field(default=None)
    search_query: str = field(default=None)
    web_research_results: Annotated[list, operator.add] = field(default_factory=list) 
    sources_gathered: Annotated[list, operator.add] = field(default_factory=list)
    research_loop_count: int = field(default=0)
    running_summary: str = field(default=None)

@dataclass(kw_only=True)
class SummaryStateInput(TypedDict):
    research_topic: str = field(default=None)

@dataclass(kw_only=True)
class SummaryStateOutput(TypedDict):
    running_summary: str = field(default=None)

query_writer_instructions="""Your goal is to generate targeted web search query.

The query will gather information related to a specific topic.

Topic:
{research_topic}

Return your query as a JSON object:
{{
    "query": "string",
    "aspect": "string",
    "rationale": "string"
}}
"""

summarizer_instructions="""Your goal is to generate a high-quality summary of the web search results.

When EXTENDING an existing summary:
1. Seamlessly integrate new information without repeating what's already covered
2. Maintain consistency with the existing content's style and depth
3. Only add new, non-redundant information
4. Ensure smooth transitions between existing and new content

When creating a NEW summary:
1. Highlight the most relevant information from each source
2. Provide a concise overview of the key points related to the report topic
3. Emphasize significant findings or insights
4. Ensure a coherent flow of information

In both cases:
- Focus on factual, objective information
- Maintain a consistent technical depth
- Avoid redundancy and repetition
- DO NOT use phrases like "based on the new results" or "according to additional sources"
- DO NOT add a preamble like "Here is an extended summary ..." Just directly output the summary.
- DO NOT add a References or Works Cited section.
"""

reflection_instructions = """You are an expert research assistant analyzing a summary about {research_topic}.

Your tasks:
1. Identify knowledge gaps or areas that need deeper exploration
2. Generate a follow-up question that would help expand your understanding
3. Focus on technical details, implementation specifics, or emerging trends that weren't fully covered

Ensure the follow-up question is self-contained and includes necessary context for web search.

Return your analysis as a JSON object:
{{ 
    "knowledge_gap": "string",
    "follow_up_query": "string"
}}"""

def generate_query(state: SummaryState):
    query_writer_instructions_formatted = query_writer_instructions.format(research_topic=state.research_topic)
    try:
        result = llm_json_mode.invoke(
            [SystemMessage(content=query_writer_instructions_formatted),
             HumanMessage(content=f"Generate a query for web search:")]
        )
        query = json.loads(result.content)
        
        return {"search_query": query['query']}
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing query JSON: {e}") 
        return {"search_query": f"information about {state.research_topic}"}

def web_research(state: SummaryState):
    search_results = tavily_search(state.search_query, include_raw_content=True, max_results=1)
     
    if not search_results or 'results' not in search_results or not search_results['results']:
        print("Warning: No search results found")
        search_str = "No search results found. The search may have failed or returned no results."
        formatted_sources = "No sources available"
    else:
        search_str = deduplicate_and_format_sources(search_results, max_tokens_per_source=1000)
        formatted_sources = format_sources(search_results)

    return {
        "sources_gathered": [formatted_sources], 
        "research_loop_count": state.research_loop_count + 1, 
        "web_research_results": [search_str]
    }

def summarize_sources(state: SummaryState):
    existing_summary = state.running_summary
    most_recent_web_research = state.web_research_results[-1]

    try:
        if existing_summary:
            human_message_content = (
                f"Extend the existing summary: {existing_summary}\n\n"
                f"Include new search results: {most_recent_web_research}\n\n"
                f"That addresses the following topic: {state.research_topic}"
            )
        else:
            human_message_content = (
                f"Generate a summary of these search results: {most_recent_web_research}\n\n"
                f"That addresses the following topic: {state.research_topic}"
            )
     
        result = llm.invoke(
            [SystemMessage(content=summarizer_instructions),
            HumanMessage(content=human_message_content)]
        )

        running_summary = result.content
        return {"running_summary": running_summary}
    except Exception as e:
        print(f"Error in summarizing sources: {e}") 
        return {"running_summary": f"Error generating summary for {state.research_topic}."}

def reflect_on_summary(state: SummaryState):
    try:
        result = llm_json_mode.invoke(
            [SystemMessage(content=reflection_instructions.format(research_topic=state.research_topic)),
            HumanMessage(content=f"Identify a knowledge gap and generate a follow-up web search query based on our existing knowledge: {state.running_summary}")]
        )   
        follow_up_query = json.loads(result.content)

        return {"search_query": follow_up_query['follow_up_query']}
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing reflection JSON: {e}") 
        return {"search_query": f"latest developments about {state.research_topic}"}

def finalize_summary(state: SummaryState):
    all_sources = "\n".join(source for source in state.sources_gathered)
    final_summary = f"## Summary\n\n{state.running_summary}\n\n### Sources:\n{all_sources}"
    return {"running_summary": final_summary}

def route_research(state: SummaryState, config: RunnableConfig) -> Literal["finalize_summary", "web_research"]:
    try:
        configurable = Configuration.from_runnable_config(config)
        max_loops = configurable.max_web_research_loops
    except Exception as e:
        print(f"Error loading configuration: {e}") 
        max_loops = 3
     
    if state.research_loop_count < max_loops:
        return "web_research"
    else:
        return "finalize_summary" 


def optimize_tavily_search(query, include_raw_content=True, max_results=3):
    """Optimized version of tavily_search that retrieves fewer results and limits content size""" 
    return tavily_search(query, include_raw_content, max_results)

def generate_efficient_query(state: SummaryState):
    """More efficient query generation that focuses on precision""" 
    query_writer_efficient_instructions = """Your goal is to generate a highly focused and specific web search query.
    The query should be concise (10 words or less) and target the most relevant information related to the topic.
    
    Topic:
    {research_topic}
    
    Return your query as a JSON object:
    {{
        "query": "string",
        "aspect": "string",
        "rationale": "string"
    }}
    """
    
    query_writer_instructions_formatted = query_writer_efficient_instructions.format(research_topic=state.research_topic)
    try:
        result = llm_json_mode.invoke(
            [SystemMessage(content=query_writer_instructions_formatted),
             HumanMessage(content=f"Generate a query for web search:")]
        )
        query = json.loads(result.content)
        
        return {"search_query": query['query']}
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing query JSON: {e}") 
        return {"search_query": f"information about {state.research_topic}"}

def build_graph():
    builder = StateGraph(SummaryState, input=SummaryStateInput, output=SummaryStateOutput, config_schema=Configuration)
    builder.add_node("generate_query", generate_query)
    builder.add_node("web_research", web_research)
    builder.add_node("summarize_sources", summarize_sources)
    builder.add_node("reflect_on_summary", reflect_on_summary)
    builder.add_node("finalize_summary", finalize_summary)

    builder.add_edge(START, "generate_query")
    builder.add_edge("generate_query", "web_research")
    builder.add_edge("web_research", "summarize_sources")
    builder.add_edge("summarize_sources", "reflect_on_summary")
    builder.add_conditional_edges("reflect_on_summary", route_research)
    builder.add_edge("finalize_summary", END)

    return builder.compile()

if __name__ == "__main__":
    try: 
        graph = build_graph()
         
        research_input = SummaryStateInput(research_topic="Edication System in India vs America")
         
        summary = graph.invoke(research_input)
         
        print("\n\n===== FINAL SUMMARY =====\n")
        print(summary['running_summary'])

        end_time = time.time()
 
        total_time = end_time - start_time
        print("\n")
        print(f"⏱️ Total time taken to generate summary: {total_time:.2f} seconds")
        
        
    except Exception as e:
        print(f"Error running research graph: {e}")