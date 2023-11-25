from setuptools import setup, find_packages

setup(
    name="autowired",
    version="0.2.10",
    description="A minimalistic dependency injection library for Python",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nicolai Großer",
    author_email="nicolai.grosser@googlemail.com",
    url="https://github.com/npgrosser/autowired",
    license="MIT",
    packages=find_packages(),
    install_requires=[],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
