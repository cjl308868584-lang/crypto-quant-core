"""Setuptools entry point for PEP 517 frontends with legacy build hooks."""

from setuptools import find_packages, setup


setup(
    name="crypto-quant-core",
    version="0.77.0",
    package_dir={"": "src"},
    packages=find_packages("src"),
    package_data={
        "crypto_quant": [
            "schemas/*.json",
            "dashboard/*.html",
            "dashboard/*.js",
            "dashboard/*.css",
            "fixtures/challenger-replacement-v076/*.json",
            "fixtures/challenger-replacement-v077/*.json",
        ]
    },
    entry_points={
        "console_scripts": [
            "crypto-quant-operations-dashboard="
            "crypto_quant.operations_dashboard:main"
        ]
    },
    install_requires=["jsonschema>=4.25,<5"],
)
