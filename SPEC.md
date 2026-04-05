1. Scope and Non-Goals
Scope: cli-core-yo MUST provide a reusable CLI kernel that downstream repositories use to build a unified command-line interface with consistent behavior, output style, help, and extension semantics.
cli-core-yo MUST be responsible for:


Building the root CLI application object and enforcing a stable command tree.


Defining and enforcing the user-facing CLI contract in Section 2.


Providing a command registration and discovery system that downstream repos use without mutating the core CLI directly.


Providing shared UX primitives (console formatting, message styles, JSON output rules, progress output rules, prompt rules).


Providing standard “meta” commands that exist in every downstream CLI:


version


info




Providing standard optional shared groups that downstream repos can enable by configuration:


config group


env group




Providing a runtime context object that is initialized once per invocation and is accessible to all commands.


Providing XDG Base Directory path resolution utilities parameterized by downstream app identity (config/data/state/cache directories).


Providing a deterministic plugin loading model (programmatic and entry-point based) for registering downstream command groups.


Non-Goals: cli-core-yo MUST NOT do any of the following:


Implement downstream, domain-specific business logic (printers, servers, AWS, databases, authentication).


Require a specific environment manager (conda, venv, poetry, uv, nix).


Modify the caller’s shell environment (no export, no cd side effects).


Implicitly create or mutate user configuration content outside explicit config commands.


Perform network operations, filesystem scanning, or subprocess execution except where explicitly defined as part of the optional shared config and env groups.


Introduce telemetry, analytics, “phone home”, background services, or auto-updaters.


Provide multiple competing CLIs or alternative UX modes beyond the defined human and JSON output rules.


Justification (locked):


The scope matches the extracted behavior from zebra_day and creates a stable base for multiple repos without coupling to any domain logic.



2. CLI Contract (User-Facing)
This section defines immutable CLI behavior. Downstream repositories MUST comply exactly.
2.1 Invocation pattern


The CLI entrypoint program name is <prog>.


Invocation MUST follow:


<prog> [GLOBAL_OPTIONS] <command_path> [COMMAND_OPTIONS] [ARGS...]




<command_path> is one or more command tokens separated by spaces.


Tokens are case-sensitive.


2.2 Command grammar


Command names MUST match the regex: ^[a-z][a-z0-9-]*$.


Command names MUST be kebab-case for multiword names.


Command hierarchy:


The CLI MUST support arbitrary depth of subcommands.


The primary expected depth is:


root command OR


root group + subcommand






Naming semantics:


Command groups (commands that have subcommands) MUST be nouns.


Leaf commands (commands that execute actions) MUST be verbs or verb phrases.




2.3 Global flags
Global flags are defined as flags accepted at the root and appear in root help output.
The root command MUST provide exactly these global flags, with these meanings:


--help


Prints help for the current command context.


MUST exit with status code 0.




--install-completion


Installs shell completion for the current shell.


MUST exit with status code 0 on success.




--show-completion


Prints the completion script to stdout.


MUST exit with status code 0 on success.




--config PATH


This flag is part of the contract only when `spec.config` is enabled.


It selects the active config file for the current invocation only.


It MUST have no short alias.


It MUST be accepted only at the root, before the subcommand path.


If PATH is relative, it MUST resolve against the current working directory and be normalized to an absolute path for runtime use.


No other global flags are part of the immutable contract.
Critical constraint:


The short flag -h MUST NOT be reserved globally, because downstream commands MUST be allowed to use -h for non-help options (this is required to preserve the zebra_day interaction pattern).


2.4 Help behavior


<prog> --help MUST display:


A Usage line.


A Commands section listing all available root-level commands and groups.


An Options section listing the global flags in Section 2.3.




<prog> invoked with no arguments MUST behave as if --help was passed:


MUST print the root help.


MUST exit 0.




<prog> <command_path> --help MUST display help scoped to that command path, including:


Usage line for that command path.


Options for that command path.


Subcommands if the command path is a group.




Help output MUST be generated using a single consistent renderer across all commands.


The renderer MUST support rich formatted help (Unicode box drawing and aligned sections) consistent with Typer’s rich help style.




2.5 Version reporting


The CLI MUST provide a root-level command named version.


<prog> version MUST:


Print exactly one line to stdout, ending with \n.


The line MUST be: <app_display_name> <app_version>


In human output mode, <app_version> MUST be rendered in cyan.


MUST exit 0.




The CLI MUST provide a root-level command named info.


<prog> info MUST:


Print a two-column information table to stdout.


Include the required base rows listed in Section 6.3.


MUST exit 0.




2.6 Exit codes
The CLI MUST use these exit codes:


0: success.


1: command executed and failed (domain/runtime failure).


2: command-line usage error (unknown command, invalid option, missing required argument, invalid option value detected by argument parsing).


130: interrupted by user (SIGINT / KeyboardInterrupt).


No other exit codes are part of the stable contract unless a downstream command explicitly documents and guarantees them.
2.7 STDOUT vs STDERR rules


Human mode


The CLI MUST write all user-facing output to STDOUT.


STDERR MUST remain unused by cli-core-yo in normal operation.




JSON mode


The CLI MUST write JSON output to STDOUT only.


STDERR MUST remain unused by cli-core-yo in normal operation.




Debug exception output


When debug mode is enabled (Section 6.6), tracebacks MUST be written to STDERR.


Debug mode MUST NOT change the human-facing error line format on STDOUT.




Justification (locked):


This matches the current zebra_day behavior and preserves piping ergonomics for existing users.


2.8 Machine-readable vs human-readable output guarantees
This CLI contract defines machine-readable output as JSON output emitted by command-specific --json/-j flags, not a global output switch.


A command that supports JSON output MUST:


Declare an option named --json with short alias -j.


Use help text exactly: Output as JSON.




When --json/-j is set:


STDOUT MUST contain valid JSON (RFC 8259 compliant) and MUST end with \n.


The output MUST NOT contain ANSI color codes.


The output MUST NOT contain line-wrapping inserted by a terminal renderer.


The command MUST NOT prompt for user input.


The command MUST suppress progress animation and non-JSON status lines on STDOUT.




JSON serialization requirements:


Indentation MUST be 2 spaces.


ensure_ascii MUST be disabled (UTF-8 output).


Keys MUST be sorted (sort_keys=true) to guarantee deterministic output.




If a command does not declare --json/-j, passing --json MUST produce a usage error (exit code 2) generated by the argument parser.

> cli-core-yo MUST provide a helper/context flag (e.g. context.json_mode == True) that is set before command execution and MUST be checked by all shared UX primitives to suppress non-JSON output automatically.

2.9 Shell-safety requirements


All outputs MUST be UTF-8.


All outputs MUST use \n line endings.


In human mode, the CLI is permitted to emit Unicode symbols and box drawing characters.


In JSON mode, output MUST NOT include any control characters other than \n.


Commands that print shell commands (notably env group) MUST print commands that are valid in both bash and zsh without requiring edits.



3. Core Architecture (Library-Facing)
This section defines the cli-core-yo library API, modules, and override rules.
3.1 Required external dependencies
cli-core-yo MUST depend on:


Typer for CLI structure and parsing.


Rich for consistent rendering of human output and help.


The dependency ranges MUST be pinned to prevent help and formatting drift:


typer>=0.21.0,<0.22.0


rich>=14.0.0,<15.0.0


click>=8.3.0,<9.0.0 (explicit constraint to match Typer runtime)


Justification (locked):


The unified “feel” depends on Typer’s rich help output and Rich rendering semantics. Unpinned major or minor upgrades change help layout and wrapping behavior.


3.2 Package layout and module responsibilities
cli-core-yo MUST provide these modules and responsibilities:


cli_core_yo/spec.py


Defines immutable configuration dataclasses (no runtime logic).


Includes CliSpec, XdgSpec, ConfigSpec, EnvSpec, PluginSpec.




cli_core_yo/runtime.py


Defines RuntimeContext dataclass.


RuntimeContext includes the effective config file path for the current invocation, after any root `--config PATH` override, or null when config is disabled.


Owns runtime initialization and access:


initialize context exactly once per invocation


expose read-only accessors for commands






cli_core_yo/xdg.py


Implements XDG Base Directory path resolution using XdgSpec.


Supports optional legacy macOS config migration rules (Section 6.4).




cli_core_yo/output.py


Implements all UX primitives (message styles, headings, tables).


Implements JSON emitter that bypasses Rich wrapping.




cli_core_yo/registry.py


Implements a command registry that is the only supported mutation mechanism for the CLI command tree.


Enforces naming rules, conflict rules, and deterministic ordering.




cli_core_yo/plugins.py


Implements deterministic plugin discovery and loading using entry points and explicit plugin lists.




cli_core_yo/app.py


Implements the top-level app factory:


create root Typer app with correct settings


register core commands (version, info)


conditionally register shared groups (config, env) based on spec


load downstream plugins and apply registrations






cli_core_yo/errors.py


Defines framework exceptions and mapping to exit codes.




3.3 Public API surface
cli-core-yo MUST expose these public entrypoints:


cli_core_yo.app.create_app(spec: CliSpec) -> typer.Typer


Creates and returns a fully constructed Typer app.


Performs plugin loading defined by spec.plugins.


Registers built-in commands and enabled shared groups.




cli_core_yo.app.run(spec: CliSpec, argv: list[str] | None) -> int


Executes the Typer app.


Returns the integer exit code.


MUST NOT call sys.exit() internally.




cli_core_yo.registry.CommandRegistry


Provides:


add_group(name, help, order)


add_command(group_path, name, callable, help, order)


add_typer_app(group_path, typer_app, name, help, order)




Performs validation and conflict detection at registration time.




cli_core_yo.runtime.get_context() -> RuntimeContext


Returns the current invocation’s context.


The returned context includes the effective config file path for the invocation, after any root `--config PATH` override, or null when config is disabled.


MUST raise a framework error if called before initialization.




3.4 Root app construction invariants
The root Typer app created by create_app() MUST be configured with:


name = spec.prog_name


help = spec.root_help


add_completion = True


no_args_is_help = True


The root app MUST NOT register any global short help flag -h.
3.5 Command discovery and registration flow
Startup MUST follow this exact sequence:


Validate CliSpec (non-empty required fields, valid regex for names).


Construct root Typer app (Section 3.4).


Initialize RuntimeContext and store it in runtime, including the effective config file path when config is enabled.


Register built-in commands:


version


info




If spec.config is not null, register built-in config group (Section 4.6).


If spec.env is not null, register built-in env group (Section 4.7).


Load plugins in deterministic order (Section 4.4) and apply registrations through CommandRegistry.


Freeze the registry:


After freezing, any registration attempt MUST raise a framework error.


> Plugin loading MUST occur after built-in commands and built-in groups are registered, and before registry freeze. Explicit plugins MUST load before entry-point plugins.

3.6 Allowed overrides vs forbidden overrides
Downstream repositories MUST be able to:


Add new command groups and commands via CommandRegistry.


Add subcommands under existing groups, including built-in groups, subject to conflict rules.


Extend info output using the info extension hook (Section 6.3).


Downstream repositories MUST NOT be able to:


Remove or replace built-in commands version and info.


Replace the help renderer or disable rich help output.


Change the meaning or availability of global flags in Section 2.3.


Change JSON serialization rules in Section 2.8.


Change iconography or color mapping rules in Section 6.1 and 6.2.


Mutate the Typer app directly (bypassing CommandRegistry).



4. Extension Model for Downstream Repositories
4.1 Downstream integration contract
Each downstream repository MUST:


Depend on cli-core-yo via pip.


Provide its own console script entrypoint (Section 5.3) that calls cli_core_yo.app.run(spec, argv=None).


Each downstream repository MUST define exactly one CliSpec instance for its CLI.
4.2 Namespacing rules


The root command namespace is shared.


Command name conflicts are forbidden:


A group name MUST be unique at its path.


A command name MUST be unique within its group path.




Built-in reserved names at root:


version


info


config (if enabled)


env (if enabled)




Downstream MUST NOT register a root command or group with any reserved name.
4.3 Conflict resolution rules
When a plugin attempts to register a command path that already exists:


If the existing node is a group and the new registration is a group:


The help text MUST match exactly, or the new help text MUST be empty.


Otherwise the CLI MUST fail at startup.




If the existing node is a command and the new registration is a command:


The CLI MUST fail at startup.




If the existing node is a group and the new registration is a command (or vice versa):


The CLI MUST fail at startup.




Failure at startup MUST:


Print a single error line using the standard error formatting (Section 6.2).


Exit with code 1.


4.4 Plugin loading model
cli-core-yo MUST support two plugin sources:


Explicit programmatic plugin list


spec.plugins.explicit is an ordered list of import paths to callables.


These callables MUST be loaded in list order.




Python entry points


Entry point group name is exactly: cli_core_yo.plugins


spec.plugins.entry_points is an ordered list of entry point names to load.


Entry points MUST be loaded in list order.




A plugin callable MUST have signature:


(registry: CommandRegistry, spec: CliSpec) -> None


Each plugin callable MUST be invoked exactly once.
If a plugin fails to import or raises during registration:


The CLI MUST fail at startup with exit code 1.


The CLI MUST print an error line naming the plugin and the exception message.


4.5 Help text merging rules


Root help MUST list commands in deterministic order:


Built-in commands in fixed order: version, info


Built-in groups in fixed order if enabled: config, env


Downstream-registered groups and commands in registration order across plugins and within each plugin




Group help MUST list subcommands in registration order.


4.6 Built-in config group contract (optional)
If spec.config is not null, cli-core-yo MUST register config group with these subcommands:


When config is enabled, cli-core-yo MUST resolve exactly one config file path per invocation.


The effective config path MUST use this precedence:


1. root `--config PATH` for the current invocation, when provided


2. otherwise the spec-defined default from `ConfigSpec.xdg_relative_path` under the resolved XDG config dir or `ConfigSpec.absolute_path`


All built-in config subcommands MUST operate on that same effective config file path.


config path


Prints the effective active config file path for the current invocation.


Exit code 0.




config init


Creates the config file at the effective config path from the configured template content.


If the config file exists and --force is not provided, MUST exit 1.


Options:


--force (no short alias): overwrite existing file.






config show


Prints the config file contents from the effective config path to stdout.


If the file does not exist, MUST exit 1.




config validate


Runs validation using the downstream-provided validator hook in ConfigSpec.


If validation passes, MUST exit 0.


If validation fails, MUST exit 1 and print validation errors.




config edit


Opens the config file in an editor (Section 6.5).


If not interactive, MUST exit 1.




config reset


Replaces config file content at the effective config path with template content.


MUST create a timestamped backup before overwriting.


Requires confirmation unless --yes is set.


Options:


--yes (no short alias): skip confirmation.






ConfigSpec MUST define:


exactly one config location source:


xdg_relative_path (relative path under XDG config dir, must not be absolute and must not contain `..`)


OR absolute_path (absolute path)


template_bytes OR template_resource (exactly one is non-null)


validator callable OR null


4.7 Built-in env group contract (optional)
If spec.env is not null, cli-core-yo MUST register env group with these subcommands:


env status


Determines active status using EnvSpec.active_env_var.


Prints active state and key paths (project root, python path, config dir).


Exit code 0.




env activate


Prints a shell command instructing the user to source the activation script.


Exit code 0.




env deactivate


Prints a shell command instructing the user to source the deactivation script.


Exit code 0.




env reset


Prints a two-step instruction sequence: deactivate then activate.


Exit code 0.




EnvSpec MUST define:


active_env_var (string)


project_root_env_var (string)


activate_script_name (string)


deactivate_script_name (string)


project_root_detection rule:


Use project_root_env_var if set and path exists, else search upward from CWD for pyproject.toml.


The first directory containing pyproject.toml is the project root.





5. Packaging and Installation Contract
5.1 Python version floor


cli-core-yo MUST support Python >=3.10.


cli-core-yo MUST NOT use features requiring Python >=3.11.


5.2 Packaging format


Distribution name MUST be cli-core-yo.


Import package name MUST be cli_core_yo.


The package MUST be buildable as:


an sdist


a wheel




The package MUST be pure Python (no compiled extensions).


5.3 Entry point strategy


cli-core-yo MUST NOT install a user-facing console script by default.


Each downstream repository MUST provide its own console script entry point that invokes cli_core_yo.app.run() with its CliSpec.


5.4 Editable vs released installs


Editable installs MUST work without requiring special environment variables.


Runtime behavior MUST be identical between editable and released installs for the same code state.


5.5 OS assumptions


Supported OSes are:


macOS


Ubuntu Linux




Filesystem assumptions:


POSIX paths


Case-sensitive behavior is not assumed




cli-core-yo MUST use XDG directories on both macOS and Linux (Section 6.4).


5.6 Shell assumptions


The CLI MUST function correctly when invoked from:


bash


zsh




Completion installation and display MUST support bash and zsh via Typer’s completion mechanism.



6. UX Invariants
These rules are non-negotiable across all downstream CLIs.
6.1 Color usage


Human output MUST use Rich markup tags for styling.


The following semantic mappings MUST be used:


Success: green


Warning: yellow


Error: red


Informational action: cyan


De-emphasis: dim


Section headings: bold




Color suppression:


If the environment variable NO_COLOR is set (to any value), the CLI MUST emit no ANSI color codes.


In JSON mode, the CLI MUST emit no ANSI color codes regardless of environment.


6.2 Output formatting primitives
cli-core-yo MUST define and downstream commands MUST use these primitives:


Heading


Format: a blank line, then [bold cyan]{TITLE}[/bold cyan], then a blank line.




Success line


Prefix: [green]✓[/green] 




Warning line


Prefix: [yellow]⚠[/yellow] 




Error line


Prefix: [red]✗[/red] 




Action line


Prefix: [cyan]→[/cyan] 




Indentation rules:


Any detail line associated with a prior status line MUST be indented by exactly 3 spaces.


Bullet details MUST use • preceded by exactly 3 spaces.


6.3 info command required content
<prog> info output MUST include these base rows:


Version: downstream app version (from CliSpec.dist_name)


Python: sys.version.split()[0]


Config Dir: XDG config dir path


This row is directory-level metadata and does not imply the active config file is XDG-relative when `ConfigSpec.absolute_path` is used.


Config File: effective active config file path for the invocation when config is enabled


Data Dir: XDG data dir path


State Dir: XDG state dir path


Cache Dir: XDG cache dir path


CLI Core: cli-core-yo version


Extension hook:


CliSpec MUST allow downstream to add additional info rows via an ordered list of callables:


each callable returns a list of (key, value) rows


rows are appended in hook order




6.4 XDG path determinism and legacy migration
XDG rules:


Config directory:


Use XDG_CONFIG_HOME if set, else ~/.config.




Data directory:


Use XDG_DATA_HOME if set, else ~/.local/share on Linux and ~/Library/Application Support on macOS.




State directory:


Use XDG_STATE_HOME if set, else ~/.local/state on Linux and ~/Library/Logs on macOS.




Cache directory:


Use XDG_CACHE_HOME if set, else ~/.cache on Linux and ~/Library/Caches on macOS.




Directories MUST be created with parents=True, exist_ok=True when resolved.
Legacy macOS migration (optional, spec-driven):


If XdgSpec.legacy_macos_config_dir is set:


For each legacy filename listed in XdgSpec.legacy_copy_files, if the legacy file exists and the XDG target file does not exist:


The CLI MUST copy the legacy file to the XDG target path.


Copy MUST preserve file metadata when the platform supports it.






6.5 Editor launching behavior (for config edit)


Editor selection order MUST be:


VISUAL


EDITOR


vi




The editor MUST be executed as a subprocess with the config file path as a single argument.


If the editor subprocess returns non-zero, the command MUST exit 1.


6.6 Verbosity levels and debug behavior


The framework defines two runtime verbosity modes:


Normal mode (default)


Debug mode




Debug mode trigger:


Debug mode is enabled if environment variable CLI_CORE_YO_DEBUG is set to 1.


Debug mode behavior:


Unhandled exceptions MUST print a traceback to STDERR.


The CLI MUST still print a single formatted error line to STDOUT using the Error line primitive.


6.7 Progress reporting rules


Progress output MUST NOT be emitted in JSON mode.


Progress output MUST be emitted only as human output and only when explicitly enabled by a command’s own flags.


If progress uses carriage returns (\r) for in-place updates:


The command MUST ensure a final newline is printed before exit.




6.8 Determinism guarantees


JSON output MUST be deterministic:


sorted keys


indentation fixed at 2


no wrapping


trailing newline




Human output order MUST be deterministic:


command list order in help is registration order (Section 4.5)


table row order is insertion order




Any output that contains timestamps MUST use ISO 8601 in UTC with a trailing Z.



7. Migration Plan from zebra_day
This section defines an exact migration sequence that preserves CLI semantics while extracting shared behavior.
7.1 What logic MUST move to cli-core-yo
From zebra_day, the following MUST be extracted or reimplemented in cli-core-yo as shared behavior:


Root Typer app construction invariants:


add_completion=True


no_args_is_help=True


Rich help output




Standard meta commands:


version


info




Command registration mechanics:


consistent ordering


conflict detection




Output primitives:


✓/⚠/✗/→ semantics


heading style


indentation rules




JSON output emitter that avoids Rich wrapping (fixes current JSON wrapping defect).


XDG directory resolution and optional macOS legacy migration mechanics.


7.2 What MUST remain local to zebra_day
The following MUST remain implemented inside zebra_day:


All domain-specific command groups:


gui, printer, template, cognito, dynamo, man




All domain-specific root commands:


status, bootstrap (unless later generalized by separate explicit decision)




Any dependencies not required for the CLI core:


FastAPI/uvicorn integrations


AWS/Dynamo/Cognito logic


printer probing and template rendering logic




7.3 Steps to migrate without breaking users


Create the new package cli-core-yo implementing Sections 2 through 6.


In zebra_day, replace the current root CLI construction with a thin wrapper:


Define a CliSpec with:


prog_name="zday"


app_display_name="zebra_day"


dist_name="zebra_day"


XDG app dir name zebra_day


config primary filename zebra-day-config.json


legacy copy filename printer_config.json and legacy macOS dir ~/Library/Preferences/zebra_day (to preserve current migration behavior)






Implement a zebra_day plugin callable that registers:


all existing subcommand groups (gui, printer, template, config, env, cognito, dynamo, man)


in the same order as current zebra_day.cli registration order




Keep the console script entry point name zday unchanged.


Ensure zday --help output still lists the same commands in the same order.


Update JSON output in zebra_day commands to use cli-core-yo JSON emitter to eliminate invalid JSON caused by Rich wrapping.


7.4 Rules for validating behavioral equivalence
Behavioral equivalence MUST be validated by automated tests that:


Invoke the CLI via Typer’s CliRunner.


Assert:


Exit codes match pre-migration behavior for the same inputs.


Help includes the same command names.


version output includes zebra_day and a version string.


info output includes required rows and correct XDG paths.


JSON outputs parse via json.loads() for every --json supporting command, including outputs containing long strings and paths.




Equivalence tolerances:


Whitespace differences in human output are allowed only where Rich help layout differs due to terminal width.


JSON output MUST be valid and MUST parse, with no tolerance exceptions.



8. Explicit “DO NOT CHANGE” Rules
Claude 4.6 MUST NOT reinterpret or redesign these items:


The CLI MUST be built on Typer and Rich with pinned minor versions as specified.


Root behavior:


No-args invocation prints help and exits 0.


Global flags are exactly --help, --install-completion, --show-completion.


No global -h help alias exists.




The root command version exists and prints exactly one line with <app_display_name> <app_version>.


The root command info exists and prints a two-column table including the base rows in Section 6.3.


Command registration order determines help listing order.


The JSON output contract:


--json/-j is the reserved option name/alias pair for JSON.


JSON output MUST be valid JSON and MUST not be wrapped.


JSON MUST be deterministic (sorted keys, indent=2, UTF-8, trailing newline).




The UX primitives MUST remain:


✓ success, ⚠ warning, ✗ error, → action


the exact color mappings in Section 6.1


the exact indentation rules in Section 6.2




Plugin loading MUST be deterministic and MUST fail fast on conflicts.



9. Open Questions (If Any)
None.
