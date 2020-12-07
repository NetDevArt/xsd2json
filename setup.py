import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="xsd2json", # Replace with your own username
    version="0.0.1",
    author="Arthur Devaux",
    author_email="arthur.devaux@university-365.com",
    description="Convert xsd to json format, with codemirror compatibility support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/NetDevArt/xsd2json",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU GENERAL PUBLIC LICENSE",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
