from __future__ import annotations

import abc
import datetime
import os
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

import gitlab
import github
import urllib3.util

from uni_chars import *

if TYPE_CHECKING:
    from configuration import Configuration

DTF = "%Y-%m-%dT%H:%M:%S.%f%z"


class Issue:
    def __init__(self, name: str, description: str, state: str, created_at: datetime.datetime,
                 closed_at: Optional[datetime.datetime], author: str, closed_by: str, assigned_to: str):
        self.name = name
        self.description = description
        self.state = state
        self.created_at = created_at
        self.closed_at = closed_at
        self.author = author
        self.closed_by = closed_by
        self.assigned_to = assigned_to


class PR:
    def __init__(self, name: str, description: str, created_at: datetime.datetime,
                 merge_status: str, merged_at: Optional[datetime.datetime], author: str,
                 merged_by: str, commit_shas: List[str], reviewers: List[str],
                 target_branch: str, source_branch: str):
        self.name = name
        self.description = description
        self.created_at = created_at
        self.merge_status = merge_status
        self.merged_at = merged_at
        self.merged_by = merged_by
        self.author = author
        self.commit_shas = commit_shas
        self.reviewers = reviewers
        self.target_branch = target_branch
        self.source_branch = source_branch


class RemoteRepository(abc.ABC):
    def __init__(self, project_path: str, access_token: str):
        self.name: str = ''
        self.path = project_path
        self.access_token = access_token
        self.host = "https://github.com"

    @property
    @abc.abstractmethod
    def issues(self) -> List[Issue]:
        pass

    @property
    @abc.abstractmethod
    def pull_requests(self) -> List[PR]:
        pass

    @property
    @abc.abstractmethod
    def members(self) -> List[str]:
        pass


class GitLabRepository(RemoteRepository):
    def __init__(self, host: str, project_path: str, access_token: str):
        super().__init__(project_path, access_token)
        self.host = host
        try:
            self.connection = gitlab.Gitlab(host, private_token=access_token)
            self.connection.auth()
        except Exception as e:
            print(f"{ERROR} Could not connect to GitLab instance at {host}, check your access token.")
            raise e

        if project_path.startswith("/"):
            project_path = project_path[1:]
        if project_path.endswith(".git"):
            project_path = project_path[:-4]
        self.project = self.connection.projects.get(project_path, lazy=False)
        self.name = self.project.name

    @property
    def issues(self) -> List[Issue]:
        var = self.project.issues.list(iterator=True)
        return [Issue(name=x.title,
                      description=x.description,
                      created_at=datetime.datetime.strptime(x.created_at, DTF),
                      closed_at=datetime.datetime.strptime(x.closed_at, DTF) if x.closed_at is not None else None,
                      state=x.state,
                      closed_by=x.attributes['closed_by']['name'] if x.state == 'closed' else '',
                      author=x.author['name'],
                      assigned_to=x.assignee['name'] if x.assignee is not None else '')
                for x in var]

    @property
    def pull_requests(self) -> List[PR]:
        var = self.project.mergerequests.list(iterator=True)
        return [PR(name=x.title,
                   description=x.description,
                   created_at=datetime.datetime.strptime(x.created_at, DTF),
                   merge_status=x.merge_status,
                   merged_at=datetime.datetime.strptime(x.merged_at, DTF) if x.merged_at is not None else None,
                   merged_by=x.merged_by['name'] if x.merged_at is not None else '',
                   author=x.author['name'],
                   commit_shas=[c.id for c in x.commits()],
                   reviewers=[r['name'] for r in x.reviewers],
                   target_branch=x.target_branch,
                   source_branch=x.source_branch)
                for x in var]

    @property
    def members(self) -> List[str]:
        return [x.name for x in self.project.members_all.list(iterator=True)]


class GithubRepository(RemoteRepository):
    def __init__(self, project_path: str, access_token: str):
        if project_path.startswith("/"):
            project_path = project_path[1:]
        if project_path.endswith(".git"):
            project_path = project_path[:-4]
        super().__init__(project_path, access_token)

        try:
            self.connection = github.Github(access_token)
        except Exception as e:
            print(f"{ERROR} Could not connect to GitHub, check your access token.")
            raise e

        self.project = self.connection.get_repo(project_path)
        self.name = self.project.name

    @property
    def issues(self) -> List[Issue]:
        var = self.project.get_issues()
        return [Issue(name=x.title,
                      description=x.body,
                      created_at=x.created_at,
                      closed_at=x.closed_at,
                      state=x.state,
                      closed_by=x.closed_by.login if x.closed_by is not None else '',
                      author=x.user.login,
                      assigned_to=x.assignee.login if x.assignee is not None else '')
                for x in var]

    @property
    def pull_requests(self) -> List[PR]:
        var = self.project.get_pulls()
        return [PR(name=x.title,
                   description=x.body,
                   created_at=x.created_at,
                   merge_status=x.mergeable_state,
                   merged_at=x.merged_at,
                   merged_by=x.merged_by.login if x.merged_by is not None else '',
                   author=x.user.login,
                   commit_shas=[c.sha for c in x.get_commits()],
                   reviewers=[r.login for r in x.get_review_requests()[0]],
                   target_branch=x.base.ref,
                   source_branch=x.head.ref)
                for x in var]

    @property
    def members(self) -> List[str]:
        return [x.name if x.name is not None else "" for x in self.project.get_contributors()]


def parse_project(project: str, gitlab_access_token: str, github_access_token: str) -> RemoteRepository:
    uri = urllib3.util.parse_url(project)
    if "gitlab" in uri.host:
        return GitLabRepository(uri.scheme + '://' + uri.host, uri.path, gitlab_access_token)
    if "github" in uri.host:
        return GithubRepository(uri.path, github_access_token)
    raise ValueError(f"{ERROR} Unknown host {uri.host}")


def parse_projects(projects_path: Path, gitlab_access_token: str, github_access_token: str) -> List[RemoteRepository]:
    projects = []
    if not projects_path.exists():
        raise FileNotFoundError(f"Projects file not found at {projects_path.absolute()}")
    with open(projects_path, 'r') as f:
        for line in f.readlines():
            if not line.strip() or line.startswith('#'):
                continue
            projects.append(line.strip())
    repos: List[RemoteRepository] = []
    for project in projects:
        repo = parse_project(project, gitlab_access_token, github_access_token)
        repos.append(repo)
    return repos


if __name__ == '__main__':
    gh = github.Github(os.environ['GITHUB_ACCESS_TOKEN'])
    repo = gh.get_repo('Slinta/MetinSpeechToData')
    issues = repo.get_issues()
    for issue in issues:
        iss = Issue(name=issue.title,
                    description=issue.body,
                    created_at=issue.created_at,
                    closed_at=issue.closed_at,
                    state=issue.state,
                    closed_by=issue.closed_by.login if issue.closed_by is not None else '',
                    author=issue.user.login,
                    assigned_to=issue.assignee.login if issue.assignee is not None else '')
        print(iss)
    prs = repo.get_pulls()
    for pr in prs:
        preq = PR(name=pr.title,
                  description=pr.body,
                  created_at=pr.created_at,
                  merge_status=pr.mergeable_state,
                  merged_at=pr.merged_at,
                  merged_by=pr.merged_by.login if pr.merged_by is not None else '',
                  author=pr.user.login,
                  commit_shas=[c.sha for c in pr.get_commits()],
                  reviewers=[r.login for r in pr.get_review_requests()[0]],
                  target_branch=pr.base.ref,
                  source_branch=pr.head.ref)
        print(preq)
        print(pr)
    members = repo.get_contributors()

    pass
