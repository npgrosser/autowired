from setuptools import setup, find_packages

setup(
    name="autowired",
    version="0.1.7",
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
)
