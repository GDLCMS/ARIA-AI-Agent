from pyngrok import ngrok

tunnel = ngrok.connect(8080)
print("=" * 50)
print("HTTPS URL for Power Automate:")
print(tunnel.public_url)
print("=" * 50)
print("Keep this window open!")
input("Press Enter to stop...")
ngrok.kill()