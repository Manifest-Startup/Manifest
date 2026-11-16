"""Shell completion: ``eval "$(manifest completion zsh)"`` (or ``bash``).

Command names are embedded in the script; options come from ``manifest __complete``
so they always match the installed catalog.
"""

from __future__ import annotations

from manifest_cli import catalog, rest

GLOBAL_FLAGS = ["--base-url", "--json", "--help"]


def command_names() -> list[str]:
    from manifest_cli.main import BUILTINS

    names = list(BUILTINS)
    names += list(rest.groups())
    names += [op["command"] for op in catalog.operations()]
    return names


def flags_for(words: list[str]) -> list[str]:
    """Options (or subcommands) for ``manifest <words…>``."""
    from manifest_cli import main as cli

    if not words:
        return command_names()
    name = words[0]
    groups = rest.groups()
    if name in groups:
        cmds = groups[name]
        if len(cmds) == 1 and not cmds[0].name:
            parser = cli.rest_parser(cmds[0])
        elif len(words) >= 2 and words[1] in {c.name for c in cmds}:
            parser = cli.rest_parser(next(c for c in cmds if c.name == words[1]))
        else:
            return [c.name for c in cmds]
    elif name == "completion":
        return ["zsh", "bash"]
    else:
        op = catalog.find(name)
        if op is None:
            return GLOBAL_FLAGS
        parser = cli.operation_parser(op)
    flags: list[str] = []
    for action in parser._actions:  # noqa: SLF001
        flags += [o for o in action.option_strings if o.startswith("--")]
    return sorted(set(flags))


_BASH = """# manifest bash completion: eval "$(manifest completion bash)"
_manifest_complete() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local words=("${COMP_WORDS[@]:1:COMP_CWORD-1}")
  local options
  if [ "${#words[@]}" -eq 0 ]; then
    options="__COMMANDS__"
  else
    options="$(manifest __complete "${words[@]}" 2>/dev/null)"
  fi
  COMPREPLY=($(compgen -W "$options" -- "$cur"))
}
complete -o default -F _manifest_complete manifest
"""

_ZSH = """#compdef manifest
# manifest zsh completion: eval "$(manifest completion zsh)"
_manifest() {
  local -a options
  if (( CURRENT == 2 )); then
    options=(__COMMANDS__)
  else
    options=(${(f)"$(manifest __complete ${words[2,CURRENT-1]} 2>/dev/null)"})
  fi
  _describe -t manifest 'manifest' options || _files
}
if [[ "${zsh_eval_context[-1]}" == "loadautofunc" ]]; then
  _manifest "$@"
else
  compdef _manifest manifest
fi
"""


def script(shell: str) -> str:
    template = _ZSH if shell == "zsh" else _BASH
    return template.replace("__COMMANDS__", " ".join(command_names()))
