"""GitLab adapter - deliberately unimplemented.

This file is the shape of the gap, not a placeholder. The captain asked for both
GitHub and GitLab; GitHub shipped first, and this records exactly what the second
one costs so the answer is "write these two methods", not "redesign the tool".

Nothing outside this module changes when it is filled in. The core never learns
that GitLab exists; :mod:`iac_review.forges` already registers the name.

To implement, using the GitLab REST API v4 with a ``GITLAB_TOKEN``:

``fetch(target)``
    Target looks like ``group/project!42``.

    * ``GET /projects/{id}/merge_requests/{iid}`` for the title and the
      ``source_branch`` / ``target_branch`` pair.
    * ``GET /projects/{id}/merge_requests/{iid}/changes`` returns one entry per
      file with ``new_path``, ``new_file`` / ``deleted_file`` / ``renamed_file``
      flags, and a ``diff`` in unified format. Feed that ``diff`` straight to
      :func:`iac_review.core.diff.changed_lines`; it is the same format GitHub's
      ``patch`` field uses, which is why that parser lives in the core.
    * ``GET /projects/{id}/repository/files/{path}/raw?ref={sha}`` for content.

``publish(result)``
    GitLab has no batch review object, so post per finding:
    ``POST /projects/{id}/merge_requests/{iid}/discussions`` with
    ``position[position_type]=text``, ``position[new_path]``,
    ``position[new_line]`` and the ``base_sha`` / ``start_sha`` / ``head_sha``
    triple from the merge request's ``diff_refs``. Findings without a line become
    a plain note on the merge request.

The normalized :class:`~iac_review.core.model.Finding` already carries everything
both forges need: ``path``, ``line``, and :meth:`Finding.render` for the body.

The diagram is the one place GitLab can do better than GitHub rather than the
same. GitHub publishes no endpoint for attaching an image to a review comment,
so the GitHub adapter can only link a diagram that is already committed. GitLab
does publish one:

    ``POST /projects/:id/uploads`` with ``multipart/form-data`` returns
    ``{"url": "/uploads/<hash>/<name>", "markdown": "![name](/uploads/...)"}``

so a GitLab adapter can upload the generated ``.drawio.svg`` and paste the
returned ``markdown`` straight into the merge request note - the picture
displays even when the file is not committed anywhere. Read the artifact from
:attr:`~iac_review.core.model.ReviewResult.diagram_path`.
"""

from __future__ import annotations

from iac_review.core.model import Changeset, ReviewResult

_MESSAGE = (
    "The GitLab adapter is not implemented yet. See the module docstring in "
    "iac_review/forges/gitlab.py for the exact API calls it needs."
)


class GitLabForge:
    """Not implemented. See the module docstring."""

    name = "gitlab"

    def fetch(self, target: str) -> Changeset:
        raise NotImplementedError(_MESSAGE)

    def publish(self, result: ReviewResult) -> None:
        raise NotImplementedError(_MESSAGE)
