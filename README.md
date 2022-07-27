# HiFi Superstar
Why use HiFi Superstar over some other JavaScript [***cough***] based bot? Because it's free of weeaboo references.

## What does it do?
What doesn't it do? Well, for now it plays music and tells horrible jokes. More features to come.

## Setup
Get yourself a copy of Python 3 [here](https://www.python.org/downloads/) and install all the required packages like this: 
``pip install -r requirements.txt``

## Running
- Create a brand spanking new application by going [here](https://discord.com/developers/).
- Go to "OAuth2", select "bot" in "Scopes" and then "Administrator" in "Bot permissions"
- Go to "Bot" and enable "Presence Intent" and "Server Members Intent"
- Copy the weird looking link, and open it in your browser
- Go back to the "Bot" tab and copy your access token, and paste it in the config.ini file
- Run ``./start.sh``

**NOTE: ** On Ubuntu *python-is-python3* package should be installed if you want to use the *start.sh* script.

## How to do stuff?
Run the ``?help`` command. Obviously.

## Contributing
If you feel like adding something new or refactoring my garbage, then go ahead - submit a pull request. I haven't been a developer in years. ¯\_(ツ)_/¯
