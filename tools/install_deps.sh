#!/bin/bash

# Script to install all system dependencies for the Recipe App
# Usage: sudo ./tools/install_deps.sh

echo "--> Updating package lists..."
apt update

echo "--> Installing System & Python basics..."
# authbind: to bind port 80 without root
# git/curl: standard tools
apt install -y python3 python3-venv curl authbind

echo "--> Installing LaTeX (This might take a while)..."
# We try to keep it minimal but functional
# texlive-latex-base: The kernel
# texlive-latex-extra: KOMA-script, geometry, enumitem, etc.
# texlive-science: siunitx (units), mhchem (chemistry)
# texlive-lang-german: babel-german
# texlive-luatex: The compiler engine
# latexmk: Automation tool
apt install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-science \
    texlive-lang-german \
    texlive-luatex \
    texlive-fonts-extra \
    latexmk

echo "--> Cleaning up..."
apt autoremove -y

echo "--> Done! System is ready for PDF generation."
