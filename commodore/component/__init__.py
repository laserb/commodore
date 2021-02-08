import re

from pathlib import Path as P
from typing import Iterable

import _jsonnet
import click

from git import Repo, BadName, GitCommandError

from commodore.git import RefError


HTTP_SSH_REPLACER = re.compile("^https?://")


class Component:
    _name: str
    _repo: Repo
    _version: str = "master"
    _dir: P

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        work_dir: P = None,
        repo_url: str = None,
        version: str = None,
        force_init: bool = False,
        directory: P = None,
    ):
        self._name = name
        if directory:
            self._dir = directory
        elif work_dir:
            self._dir = component_dir(work_dir, self.name)
        else:
            raise click.ClickException(
                "Either `work_dir` or `directory` must be provided."
            )
        self._init_repo(force_init)
        if repo_url:
            self.repo_url = repo_url
        if version:
            self.version = version

    def _init_repo(self, force: bool):
        path = self.target_directory
        if not force and path.exists():
            self._repo = Repo(path)
        else:
            self._repo = Repo.init(path)

    @property
    def name(self) -> str:
        return self._name

    @property
    def repo(self) -> Repo:
        return self._repo

    @property
    def repo_url(self) -> str:
        return self._repo.remote().url

    @repo_url.setter
    def repo_url(self, url: str):
        try:
            self._repo.remote().set_url(url)
        except ValueError:
            self._repo.create_remote("origin", url)
        # Try to generate a best effort push-over-SSH URL. If the URL starts
        # with http/https, replace the protocol prefix with ssh://git@,
        # otherwise return the url string unchanged.
        pushurl = HTTP_SSH_REPLACER.sub("ssh://git@", url)
        self._repo.remote().set_url(pushurl, push=True)

    @property
    def version(self) -> str:
        return self._version

    @version.setter
    def version(self, version: str):
        self._version = version

    @property
    def target_directory(self) -> P:
        return self._dir

    @property
    def class_file(self) -> P:
        return self.target_directory / "class" / f"{self.name}.yml"

    @property
    def defaults_file(self) -> P:
        return self.target_directory / "class" / "defaults.yml"

    @property
    def lib_files(self) -> Iterable[P]:
        lib_dir = self.target_directory / "lib"
        if lib_dir.exists():
            return lib_dir.iterdir()

        return []

    @property
    def filters_file(self) -> P:
        # The command `component compile` changes directory so we need an absolute path here.
        # TODO Use self.target_directory when implement https://github.com/projectsyn/commodore/issues/214.
        return P(self.repo.working_tree_dir, "postprocess", "filters.yml")

    @property
    def parameters_key(self):
        return component_parameters_key(self.name)

    def checkout(self):
        remote_heads = self._repo.remote().fetch()
        remote_prefix = self._repo.remote().name + "/"
        for head in remote_heads:
            branch = head.name
            if branch.startswith(remote_prefix):
                branch = branch.replace(remote_prefix, "", 1)
            if branch == self._version:
                commit = head.commit
                break
        else:
            # If we haven't found a branch matching the requested version,
            # assume the version is a commit sha.
            commit = self._version
            branch = None

        try:
            if branch:
                # If we found a remote branch for the requested version, find
                # or create a local branch and point HEAD to the branch.
                _head = [h for h in self._repo.heads if h.name == branch]
                if len(_head) > 0:
                    head = _head[0]
                    head.commit = commit
                else:
                    head = self._repo.create_head(branch, commit=commit)

                head.set_tracking_branch(self.repo.remote().refs[branch])
                self._repo.head.reference = head
            else:
                # Create detached head by setting repo.head.reference as
                # direct ref to commit object.
                rev = self._repo.rev_parse(commit)
                self._repo.head.reference = rev

            # Reset working tree to current HEAD reference
            self._repo.head.reset(index=True, working_tree=True)
        except GitCommandError as e:
            raise RefError(f"Failed to checkout revision '{self.version}'") from e
        except BadName as e:
            raise RefError(f"Revision '{self.version}' not found in repository") from e

    def render_jsonnetfile_json(self, component_params):
        """
        Render jsonnetfile.json from jsonnetfile.jsonnet
        """
        jsonnetfile_jsonnet = self._dir / "jsonnetfile.jsonnet"
        jsonnetfile_json = self._dir / "jsonnetfile.json"
        if jsonnetfile_jsonnet.is_file():
            if jsonnetfile_json.name in self.repo.tree():
                click.secho(
                    f" > [WARN] Component {self.name} repo contains both jsonnetfile.json and jsonnetfile.jsonnet, "
                    + "continuing with jsonnetfile.jsonnet",
                    fg="yellow",
                )
            # pylint: disable=c-extension-no-member
            output = _jsonnet.evaluate_file(
                str(jsonnetfile_jsonnet),
                ext_vars=component_params.get("jsonnetfile_parameters", {}),
            )
            with open(self._dir / "jsonnetfile.json", "w") as fp:
                fp.write(output)


def component_dir(work_dir: P, name: str) -> P:
    return work_dir / "dependencies" / name


def component_parameters_key(name: str) -> str:
    return name.replace("-", "_")
