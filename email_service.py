import mailtrap as mt
from config import MAILTRAP_API_TOKEN, NET, BLOCK_EXPLORER


def send_welcome_email(email, moniker):
    mail = mt.Mail(
        sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
        to=[mt.Address(email=email)],
        subject="Welcome to Heavymeta Collective",
        html=f"""
        <h1>Welcome, {moniker}!</h1>
        <p>You're now part of the Heavymeta Collective.</p>
        <p>Log in to customize your profile and link-tree.</p>
        """,
    )
    client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
    client.send(mail)


def send_launch_key_email(email, launch_key_secret, stellar_address):
    acct_url = f"{BLOCK_EXPLORER}/account/{stellar_address}"
    mail = mt.Mail(
        sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
        to=[mt.Address(email=email)],
        subject="Your Pintheon Launch Key",
        html=f"""
        <h1>Your Launch Key</h1>
        <p><strong>Save this securely. You need it + your Launch Token to start your
        Pintheon node.</strong></p>
        <code>{launch_key_secret}</code>
        <h3>Node Address</h3>
        <p>{stellar_address}</p>
        <a href="{acct_url}">{acct_url}</a>
        """,
    )
    client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
    client.send(mail)
