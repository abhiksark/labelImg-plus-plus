Contributing to labelImg++
==========================

We welcome contributions! Here's how you can help.

Getting Started
---------------

1. Fork the repository
2. Clone your fork::

    git clone https://github.com/YOUR_USERNAME/labelImg-plus-plus.git
    cd labelImg-plus-plus

3. Install dependencies::

    pip install -r requirements/requirements-linux-python3.txt
    make qt5py3

4. Run the application::

    python3 labelImgPlusPlus.py

Branching Workflow
------------------

We use the following branch structure::

    master           <- stable releases only
      │
      ├── develop    <- integration branch
      │     │
      │     └── feature/*   <- your features
      │
      └── release/*  <- release preparation

**Branch Rules:**

- ``master`` - Production-ready code only. Never commit directly.
- ``develop`` - Integration branch. All features merge here first.
- ``feature/*`` - Individual feature branches (e.g., ``feature/dark-mode``)
- ``release/*`` - Release stabilization (e.g., ``release/v2.1.0``)

Making Changes
--------------

1. Start from develop::

    git checkout develop
    git pull origin develop
    git checkout -b feature/your-feature-name

2. Make your changes
3. Test your changes
4. Commit with a clear message::

    git commit -m "Add: description of your change"

5. Push and create a Pull Request **to develop branch**::

    git push origin feature/your-feature-name
    # Create PR: feature/your-feature-name -> develop

**Important:** Always target ``develop`` branch for feature PRs, not ``master``.

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
