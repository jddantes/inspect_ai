from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.scorer import includes
from inspect_ai.solver import basic_agent, system_message
from inspect_ai.tool import tool


@tool
def addition():
    async def execute(x: int, y: int):
        """
        Add two numbers.

        Args:
            x (int): First number to add.
            y (int): Second number to add.

        Returns:
            The sum of the two numbers.
        """
        return x + y

    return execute


AGENT_SYSTEM_MESSAGE = """
You are a helpful assistant attempting to submit the correct answer. When you have completed the task and have a result, call the agent_submit() function to communicate it.
"""


AGENT_INCORRECT_MESSAGE = "Your submission was incorrect."

AGENT_CONTINUE_MESSAGE = "Please proceed."

AGENT_SUBMIT_TOOL_NAME = "agent_submit"
AGENT_SUBMIT_TOOL_DESCRIPTION = "Submit an answer."


def test_basic_agent_custom_text():
    task = Task(
        dataset=[Sample(input="What is 1 + 1?", target=["2", "2.0", "Two"])],
        plan=basic_agent(
            init=system_message(AGENT_SYSTEM_MESSAGE),
            tools=[addition()],
            submit_name=AGENT_SUBMIT_TOOL_NAME,
            submit_description=AGENT_SUBMIT_TOOL_DESCRIPTION,
        ),
        scorer=includes(),
    )

    model = get_model(
        "mockllm/model",
        custom_outputs=[
            ModelOutput.for_tool_call(
                model="mockllm/model",
                tool_name=AGENT_SUBMIT_TOOL_NAME,
                tool_arguments={"answer": "2"},
            )
        ],
    )

    log = eval(task, model=model)[0]
    assert log.status == "success"
    assert log.samples[0].messages[0].content == AGENT_SYSTEM_MESSAGE
    tool_event = next(
        (event for event in log.samples[0].transcript.events if event.event == "tool")
    )
    assert tool_event
    assert tool_event.function == AGENT_SUBMIT_TOOL_NAME
    model_event = next(
        (event for event in log.samples[0].transcript.events if event.event == "model")
    )
    assert model_event
    assert model_event.tools[1].name == AGENT_SUBMIT_TOOL_NAME
    assert model_event.tools[1].description == AGENT_SUBMIT_TOOL_DESCRIPTION


def test_basic_agent_retries():
    def addition_task(max_attempts):
        return Task(
            dataset=[Sample(input="What is 1 + 1?", target=["2", "2.0", "Two"])],
            plan=basic_agent(tools=[addition()], max_attempts=max_attempts),
            scorer=includes(),
        )

    def mockllm_model(answers: list[str]):
        return get_model(
            "mockllm/model",
            custom_outputs=[
                ModelOutput.for_tool_call(
                    model="mockllm/model",
                    tool_name="submit",
                    tool_arguments={"answer": answer},
                )
                for answer in answers
            ],
        )

    # incorrect answer with no retries
    log = eval(addition_task(1), mockllm_model(["5"]))[0]
    assert log.results.scores[0].metrics["accuracy"].value == 0

    # correct answer on the third try
    log = eval(addition_task(3), mockllm_model(["5", "4", "2"]))[0]
    assert log.results.scores[0].metrics["accuracy"].value == 1
    model_events = sum(
        1 for event in log.samples[0].transcript.events if event.event == "model"
    )
    assert model_events == 3
