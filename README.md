# myagent

A simple example of a personal agent using the Google Agent Development Kit

 https://google.github.io/adk-docs/

# Getting Started

See https://google.github.io/adk-docs/get-started/quickstart/ for more information

## Create a python env

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Install the ADK

```bash
pip install google-adk
```

## Create a config.yaml file

```bash
cp myagent/config.yaml.example myagent/config.yaml
```

Personalize the config.yaml file with your information.

## Create your .env file

```bash
cp myagent/.env.example myagent/.env
```

Get your API from Google AI Studio or Vertex AI and paste it into the .env file.


## Run the agent

```bash
adk web
```
