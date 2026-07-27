"""Setuptools entry point for PEP 517 frontends with legacy build hooks."""

from setuptools import find_packages, setup


setup(
    name="crypto-quant-core",
    version="0.19.0",
    package_dir={"": "src"},
    packages=find_packages("src"),
    package_data={"crypto_quant": ["schemas/*.json"]},
    install_requires=["jsonschema>=4.25,<5"],
)
