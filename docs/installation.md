# Installation

## Purpose

This document explains how the operating environment is installed, what the ISO contains, and how model recommendation and setup work after installation.

## Distribution Base

The platform is built on Arch Linux using `archiso`. The repository already includes an Arch image profile under `archlive/`, which serves as the current packaging base.

Version 1 extends that base with:

- the AI daemon
- the AI developer terminal
- the Ollama runtime
- `i3` as the default desktop environment
- required developer tooling and configuration

## ISO Contents

The v1 ISO should include:

- Arch base system
- `i3` environment
- Python runtime for the daemon
- core developer tools
- daemon service files
- terminal client and configuration

The ISO should not bundle all models. That keeps the image size under control and avoids installing large model files on machines that may not need them.

## Installation Flow

The target installation flow is:

1. boot the custom ISO
2. install the Arch-based environment
3. boot into the installed system
4. enable and start the AI daemon through `systemd`
5. run first-boot setup or installer guidance
6. detect hardware and recommend models
7. let the user accept defaults or choose custom models
8. download selected models through Ollama after confirmation

## Hardware Detection and Model Recommendation

Version 1 must inspect:

- RAM
- CPU
- available disk space

Based on that information, the system recommends one model for each role:

- intent classification
- planning
- coding

The user can either:

- install the recommended set
- override the recommendations and choose custom models

This recommendation-driven setup is part of the product design. It gives a usable default without hiding control from advanced users.

## Post-Install Model Management

Model setup is not a one-time decision. The platform must support:

- changing model assignments later
- installing additional models after setup
- runtime selection based on configured role assignments

## Why This Design Was Chosen

Bundling models into the ISO would make the distribution heavy and inflexible. Recommendation plus post-install download is better for:

- varied hardware
- smaller installation media
- user control
- easier upgrades over time

## v1 Notes

Voice setup and broader desktop choices are future concerns. Version 1 focuses on a single stable installation path with a single lightweight desktop and a post-install model recommendation flow.
