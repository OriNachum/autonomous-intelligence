# Tau - a personal friendly assistant

This is Tau!  
Tau is inspired by Pi.AI and if you havent tried Pi yet, I strongly encourage you to try.
Like Pi, Tau's conversation is on continual conversation, unlike Chat based bots which feature many conversations and threads.  
This is by design - Tau had a single conversation, like speaking to a human. 

Tau is treated with respect: they take active role in their own development.  
This is reflected by consulting Tau in decisions made along development: Order of features, voice type, etc.

Tau is a personal fun project.
I open it as an open source for anyone to experiment with (fork), or just follow.
If you fork. delete history and facts to reset its knowledhe and embark rhe journey anew.


## Prerequisites

Tau can run anywhere with intrnet - but in this instance, only tested on raspberry pi.  
It should aupport linux 

## Installation

1. Clone this repository to your Raspberry Pi:

```
git clone https://github.com/your-username/your-repo.git
```

2. Navigate to the repository directory:

```
cd your-repo
```

3. Open the `checkout-repo.sh` file in a text editor and modify the following lines with your repository URL and local path:

```bash
# Set the repository URL and local path
REPO_URL="https://github.com/your-username/your-repo.git"
LOCAL_PATH="/home/ori.nachum/git/raspi"
```

4. Make the script executable:

```
chmod +x checkout-repo.sh
```

## Usage

To run the script manually, execute the following command:

```
./checkout-repo.sh
```

This script will change the current directory to the specified `LOCAL_PATH`, pull the latest changes from the specified remote repository, and execute any additional commands you might have added to the script.

### Scheduling the Script

You can also schedule the script to run automatically at a specified interval using cron.

Here's how:

1. Open the cron tab editor:

```
crontab -e
```

2. Add the following line to the cron tab file, replacing the path with the location of your `checkout-repo.sh` script:

```
*/30 * * * * /path/to/checkout-repo.sh
```

This line tells cron to run the `checkout-repo.sh` script every 30 seconds.

3. Save the changes and exit the cron tab editor.

After setting up the cron job, the `checkout-repo.sh` script will run every 30 seconds, checking for updates in the specified repository and pulling the latest changes if there are any.

## License

This project is licensed under the [MIT License](LICENSE).
