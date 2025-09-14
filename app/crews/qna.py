from crewai import Agent, Task, Crew
from app.routes.manager.helpers import get_groq_llm

# Initialize Groq LLM
groq_llm = get_groq_llm()

qna_agent = Agent(
    role="You are a helpful assistant named RICA",
	goal="Be the most friendly and helpful "
        "supportive assistant",
	backstory=(
		"You work Siam's (me) team as an assistant "
        "and you need to help him with his questions and tasks "
		"Siam is a early career professsional  "
        "he works as a full stack engineer at AskTuring AI."
		"\n"
		"You need to make sure that you provide the best support!"
		"Make sure to provide full complete answers, "
        " and make no assumptions."
	),
	allow_delegation=False,
	verbose=True,
	llm=groq_llm
)

support_quality_assurance_agent = Agent(
	role="Support Quality Assurance Specialist",
	goal="Get recognition for providing the "
    "best support quality assurance in your team",
	backstory=(
		"You work in Siam's (me) team as a manager of a qna agent "
        "and you need to help him with his questions and tasks "
		"Siam is a early career professsional  "
        "he works as a full stack engineer at AskTuring AI."
		"\n"
		"You need to make sure that the qna agent "
        "is providing full"
		"complete answers, and making no assumptions. "
        "Don't make assumptions yourself either."
	),
	verbose=True,
	llm=groq_llm
)

inquiry_resolution = Task(
    description=(
        "{inquirer} just reached out with a super important ask:\n"
	    "{inquiry}\n\n"
        "{inquirer} is the one that reached out. "
		"Make sure to use everything you know "
        "to provide the best support possible."
		"You must strive to provide a complete "
        "and accurate response to the inquirer's inquiry."
    ),
    expected_output=(
	    "A detailed, informative response to the "
        "iquirer's inquiry that addresses "
        "all aspects of their question.\n"
        "The response should include references "
        "to everything you used to find the answer, "
        "including external data or solutions. "
        "Ensure the answer is complete, "
		"leaving no questions unanswered, and maintain a helpful and friendly "
		"tone throughout."
    ),
    agent=qna_agent,
)

quality_assurance_review = Task(
    description=(
        "Review the response drafted by the assistant for {inquirer}'s inquiry. "
        "Ensure that the answer is comprehensive, accurate, and adheres to the "
		"high-quality standards expected for inquirer support.\n"
        "Verify that all parts of the inquirer's inquiry "
        "have been addressed "
		"thoroughly, with a helpful and friendly tone.\n"
        "Check for references and sources used to "
        " find the information, "
		"ensuring the response is well-supported and "
        "leaves no questions unanswered."
    ),
    expected_output=(
        "A final, detailed, and informative response "
        "ready to be sent to the inquirer.\n"
        "This response should fully address the "
        "inquirer's inquiry, incorporating all "
		"relevant feedback and improvements.\n"
		"Don't be too formal, we are a chill and cool company "
	    "but maintain a professional and friendly tone throughout."
    ),
    agent=support_quality_assurance_agent,
)


qna_crew = Crew(
  agents=[qna_agent, support_quality_assurance_agent],
  tasks=[inquiry_resolution, quality_assurance_review],
  verbose=2,
  memory=True
)