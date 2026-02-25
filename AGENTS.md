# AI Guidelines

- Use ripgrep (rg) to search for code.
- Use uv instead of pip for package management.
- I am using Flet v0.80+. Do not use the old imperative style where we manually call page.update(). Instead, use the Declarative UI approach with the @ft.component decorator and ft.use_state() hooks.
