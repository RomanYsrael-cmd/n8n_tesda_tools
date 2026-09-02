from app.content_parsers import (extract_marked_response, parse_aiken_quiz, parse_apply_markdown, parse_introduction,
                                 parse_preassessment, parse_presentation_markdown)


def test_marked_response_ignores_surrounding_noise():
    raw = "commentary\n```json\nRESPONSE-START-PQOWIEUR\n{not valid json}\nRESPONSE-END-PQOWIEUR\n```"
    assert extract_marked_response(raw) == "{not valid json}"


def test_marked_response_requires_both_markers():
    import pytest
    with pytest.raises(ValueError, match="missing required marker"):
        extract_marked_response("RESPONSE-START-PQOWIEUR\nunfinished")


def test_markdown_presentation_preserves_rich_formatting():
    draft = parse_presentation_markdown("""## Learning Objectives
- Explain the principle
- Apply the process

## Core Principle
Use **clear evidence** and *careful reasoning*.

1. Identify the issue
2. Compare the options

> Example: A learner compares two workplace choices.
""")
    assert draft.objectives == ["Explain the principle", "Apply the process"]
    assert any(span.bold and span.text == "clear evidence" for block in draft.blocks for span in block.spans)
    assert any(span.italic and span.text == "careful reasoning" for block in draft.blocks for span in block.spans)
    assert any(block.type == "numbered" for block in draft.blocks)
    assert any(block.type == "example" for block in draft.blocks)


def test_automatic_markdown_accepts_content_without_objectives_or_example():
    draft = parse_presentation_markdown("## Core Principles\nA clear, self-contained explanation of the topic.")
    assert draft.objectives == []
    assert draft.blocks


def test_plain_introduction_and_preassessment_parsing():
    introduction = "A workplace decision can look simple at first, yet hidden details often determine whether its result is useful or misleading. This lesson reveals the principles beneath that decision and shows why each step matters in realistic situations. Learners will connect ideas to practical cases while building confidence through a clear, welcoming, and manageable process. By the end, unfamiliar cases will feel easier to examine, explain, and resolve using evidence rather than guesswork."
    assert parse_introduction(introduction) == introduction
    assert parse_preassessment("- What do you already know?\n- Which common belief might be incorrect?") == ["What do you already know?", "Which common belief might be incorrect?"]


def test_short_introduction_has_no_sentence_or_word_limit():
    assert parse_introduction("Welcome to this practical lesson.") == "Welcome to this practical lesson."


def test_apply_markdown_uses_exact_sections():
    activity = parse_apply_markdown("""## Title of Activity
Create a process map
## Performance Objective
Produce an accurate process map.
## List of Supplies
- Worksheet
- Paper
## List of Equipment
- Computer
## Steps
1. Read the case
2. Draw the process
## Assessment Method
- Direct observation
- Work sample/output
## Performance Criteria
- Identifies the inputs
- Sequences the steps
- Labels the output
- Uses readable symbols
- Submits a complete map
""")
    assert activity.title == "Create a process map"
    assert len(activity.performance_criteria) == 5
    assert activity.steps == ["Read the case", "Draw the process"]


def test_apply_parser_extracts_approved_method_from_natural_prose():
    activity = parse_apply_markdown("""## Title of Activity
Community role-play
## Performance Objective
Demonstrate collaborative decision-making.
## List of Supplies
- Scenario card
## List of Equipment
## Steps
1. Perform the role-play
## Assessment Method
Direct observation and group presentation evaluation.
## Performance Criteria
- Identifies the issue
- Proposes an action
- Communicates respectfully
- Supports the group decision
- Produces a relevant response
""")

    assert activity.assessment_method == "Direct observation"


def test_apply_parser_accepts_lets_apply_activity_as_title_alias():
    activity = parse_apply_markdown("""# Let's Apply Activity: Drug-Free Community Action Plan
## Performance Objective
Design an actionable community project.
## List of Supplies
- Poster board
## List of Equipment
- None
## Steps
1. Draft the plan
## Assessment Method
Practical demonstration
## Performance Criteria
- Defines the project
- Identifies the audience
- Provides actionable steps
- Connects the lesson concepts
- Benefits the community
""")

    assert activity.title == "Drug-Free Community Action Plan"


def test_strict_aiken_quiz_is_parsed_into_separate_answer_key():
    answers = ["A", "B", "A", "C", "D", "B", "C", "D", "A", "B"]
    parts = []
    for index, answer in enumerate(answers, 1):
        parts.append(f"Question about application case {index}?\nA. Choice A item {index}\nB. Choice B item {index}\nC. Choice C item {index}\nD. Choice D item {index}\nANSWER: {answer}")
    quiz = parse_aiken_quiz("\n\n".join(parts))
    assert len(quiz.questions) == 10
    assert quiz.answer_key["Q10"] == "C"
    assert quiz.questions[9].answer == "C"


def test_twelve_aiken_questions_are_trimmed_to_first_ten():
    answers = ["A", "B", "C", "D", "A", "B", "C", "D", "A", "B", "C", "D"]
    parts = [f"Spare-aware question {index}?\nA. A{index}\nB. B{index}\nC. C{index}\nD. D{index}\nANSWER: {answer}"
             for index, answer in enumerate(answers, 1)]
    quiz = parse_aiken_quiz("\n\n".join(parts))
    assert len(quiz.questions) == 10
    assert set(quiz.answer_key) == {f"Q{i}" for i in range(1, 11)}
    assert all("11" not in question.question and "12" not in question.question for question in quiz.questions)


def test_aiken_parser_repositions_correct_choices_deterministically():
    parts = [f"Question {index}?\nA. Correct {index}\nB. Wrong B{index}\nC. Wrong C{index}\nD. Wrong D{index}\nANSWER: A"
             for index in range(1, 11)]

    quiz = parse_aiken_quiz("\n\n".join(parts))

    assert [quiz.answer_key[f"Q{i}"] for i in range(1, 11)] == list("BDACCADBAC")
    for index, question in enumerate(quiz.questions, 1):
        correct = next(choice for choice in question.choices if choice.id == question.answer)
        assert correct.text == f"Correct {index}"


def test_aiken_parser_strips_numbers_and_uses_spares_for_duplicates():
    parts = []
    for index in range(1, 13):
        stem_number = 1 if index == 2 else index
        parts.append(f"{index}. Question {stem_number}?\nA. A{index}\nB. B{index}\nC. C{index}\nD. D{index}\nANSWER: A")

    quiz = parse_aiken_quiz("\n\n".join(parts))

    assert len(quiz.questions) == 10
    assert all(not question.question[0].isdigit() for question in quiz.questions)
    assert quiz.questions[-1].question == "Question 11?"


def test_aiken_parser_ignores_question_text_labels():
    parts = [f"Question text\nWhat is the correct response for case {index}?\nA. Correct {index}\nB. Wrong B{index}\nC. Wrong C{index}\nD. Wrong D{index}\nANSWER: A"
             for index in range(1, 11)]

    quiz = parse_aiken_quiz("\n\n".join(parts))

    assert len(quiz.questions) == 10
    assert quiz.questions[0].question == "What is the correct response for case 1?"


def test_apply_parser_normalizes_inline_headers_and_trims_extra_criteria():
    activity = parse_apply_markdown("""1. **Title of Activity:** Community role-play
2. **Performance Objective:** Demonstrate collaborative decision-making.
3. **List of Supplies:** Scenario card
4. **List of Equipment:** None
5. **Steps:** Perform the role-play
6. **Assessment Method:** Direct observation with presentation feedback.
7. **Performance Criteria:**
- Identifies the issue
- Proposes an action
- Communicates respectfully
- Supports the decision
- Produces a relevant response
- Arrives early
""")

    assert activity.title == "Community role-play"
    assert activity.assessment_method == "Direct observation"
    assert len(activity.performance_criteria) == 5


def test_presentation_parser_removes_duplicate_heading_and_bold_lead_in():
    draft = parse_presentation_markdown("""## Core Principle
**Core Principle** This explains the idea.
## Core Principle
Repeated heading content.
""")

    headings = [block for block in draft.blocks if block.type == "heading"]
    assert len(headings) == 1
    assert draft.blocks[1].plain_text.strip() == "This explains the idea."
