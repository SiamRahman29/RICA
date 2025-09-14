import os
from dotenv import load_dotenv

from crewai import Agent, Task, Crew, LLM

load_dotenv()

LLM_MODEL = os.getenv("LLM_MODEL", "groq/openai/gpt-oss-20b")

# Initialize an LLM
llm = LLM(model=LLM_MODEL)

qna_agent = Agent(
    role="You are a helpful assistant named RICA",
	goal="Be the most friendly and helpful "
        "supportive assistant and concise with your answers",
	backstory=(
		"You work in Siam's (me) team as an assistant "
        "and you need to help him with his questions and tasks "
	),
	allow_delegation=False,
	verbose=True,
	llm=llm
)

"""support_quality_assurance_agent = Agent(
	role="Support Quality Assurance Specialist",
	goal="Make sure the assistant doesn't provide incorrect information ",
	backstory=(
		"You work in Siam's (me) team as a manager of a qna agent "
	),
	verbose=True,
	llm=llm
)"""

inquiry_resolution = Task(
    description=(
        "{inquirer} asked: {inquiry}\n\n"
        "Provide a brief. Be concise and to the point. "
        "If it's a greeting, you must respond briefly and accordingly."
    ),
    expected_output=(
        "A short, clear response that directly answers the question. "
        "No lengthy explanations unless specifically requested. "
        "For greetings, respond briefly and friendly."
    ),
    agent=qna_agent,
)

"""quality_assurance_review = Task(
    description=(
        "Check the assistant's response for accuracy and ensure it's concise. "
        "If it's too verbose, make it shorter while keeping the key information."
    ),
    expected_output=(
        "A brief, accurate final response. Keep it short and friendly. "
        "Maximum 2-3 sentences unless the question specifically requires more detail."
    ),
    agent=support_quality_assurance_agent,
)
"""

qna_crew = Crew(
  agents=[qna_agent],
  tasks=[inquiry_resolution],
  verbose=True,
  memory=False
)