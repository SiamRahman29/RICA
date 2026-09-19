"""docs route: retrieval per plan mode, and the <doc> context for the answer prompt."""

from dataclasses import replace

from rica.context.evidence import Evidence, render
from rica.nodes.understand import Plan
from rica.retrieval.search import Chunk, DocSearch
from rica.routes import enabled_names

SNIPPET_CHARS = 600


def retrieve(search: DocSearch, plan: Plan) -> list[Chunk]:
    q = plan.standalone_query
    about_me = plan.doc_filter == "about_me"

    def run(about: bool) -> list[Chunk]:
        if plan.doc_mode == "whole_doc":
            return search.whole_doc(plan.doc_hint, q, about)
        if plan.doc_mode == "find_docs":
            return [replace(c, text=c.text[:SNIPPET_CHARS]) for c in search.find_docs(q, about)]
        return search.facts(q, about)

    # The planner can mislabel a question as about_me; retry over all notes
    return run(about_me) or (run(False) if about_me else [])


def docs_context(status: str | None, mode: str, packed: list[Evidence], name: str) -> str:
    if status is None:
        return ""
    if status == "error":
        return f"<doc_search status=\"error\">{name}'s notes couldn't be searched right now. Say so.</doc_search>"
    if status == "not_found" or not packed:
        offer = " Offer to search the web instead." if "web" in enabled_names() else ""
        return (
            f"<doc_search status=\"not found\">Nothing in {name}'s notes matched this request.</doc_search>\n"
            f"Tell {name} you couldn't find it in their notes; don't guess.{offer}"
        )
    intro = {
        "facts": f"Excerpts from {name}'s notes:",
        "whole_doc": f"The note {name} asked about (if it is long, only its most relevant sections):",
        "find_docs": f"The notes that best match. List every one that is relevant (title and path), each with one line on what it says about this:",
    }[mode]
    return f"{intro}\n\n{render(packed)}"
