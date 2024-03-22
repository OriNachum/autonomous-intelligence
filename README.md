# Automatic Repository Checkout

This repository contains a script that automatically checks out the latest changes from a specified Git repository on your Raspberry Pi.

## Prerequisites

Before you can use this script, make sure you have the following prerequisites installed on your Raspberry Pi:

- Git

You can install Git with the following command:

```
sudo apt-get install git
```

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
