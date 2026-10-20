# Live Houdini and Unreal sessions

No Houdini 20.x or Unreal 5.4 / 5.5 install was available when this note was written, so no `NB_WARNINGS` list, screenshot, or application version was collected.

The generated scripts are still checked only against the recording fakes in `tests/fakes/`. COP2 parameter names (`minlum`, `shapetype`, `sx`, `sy`, and the rest) follow the documented node types and are reported by `nb_set` if a live Houdini build does not have them. Do not treat a green pytest run as a live DCC run.

When a live session happens, save the version, the warning list, and a screenshot next to the example, then fix any parameter name the session rejects.
