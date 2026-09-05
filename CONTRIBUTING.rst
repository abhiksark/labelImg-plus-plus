Contributing to labelImg++
==========================

We welcome contributions! Here's how you can help.

Getting Started
---------------

1. Fork the repository
2. Clone your fork::

    git clone https://github.com/YOUR_USERNAME/labelImg-plus-plus.git
    cd labelImg-plus-plus

3. Use Python 3.10 or newer and install the project with test dependencies::

    python3 -m pip install -e . pytest

4. Run the application::

    python3 labelImgPlusPlus.py

Branching Workflow
------------------

We use the following branch structure::

    master           <- stable releases only
      │
      ├── dev        <- integration branch
      │     │
      │     └── feature/*, fix/*, chore/*   <- proposed changes
      │
      └── release/*  <- release preparation

**Branch Rules:**

- ``master`` - Production-ready code only. Never commit directly.
- ``dev`` - Integration branch. Feature, fix, and chore PRs target this branch.
- ``feature/*``, ``fix/*``, ``chore/*`` - Reviewable change branches
- ``release/*`` - Release stabilization (e.g., ``release/v4.0.0``)

Making Changes
--------------

1. Start from ``dev``::

    git checkout dev
    git pull origin dev
    git checkout -b feature/your-feature-name

2. Make your changes
3. Test your changes
4. Commit with a Conventional Commit subject::

    git commit -m "feat(scope): add the change"

5. Push and create a Pull Request **to the dev branch**::

    git push origin feature/your-feature-name
    # Create PR: feature/your-feature-name -> dev

**Important:** Target ``dev`` for feature, fix, and chore PRs, not ``master``.

Code Style
----------

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add comments for complex logic

Reporting Issues
----------------

- Check existing issues before creating a new one
- Include steps to reproduce the bug
- Include Python version and OS information

Original Contributors
---------------------

- `Tzutalin <https://github.com/tzutalin>`_ (original LabelImg creator)
- `LabelMe <http://labelme2.csail.mit.edu/Release3.0/index.php>`_
- Ryan Flynn
- All contributors to the original LabelImg project

labelImg++ Contributors
-----------------------

- Abhik Sarkar
