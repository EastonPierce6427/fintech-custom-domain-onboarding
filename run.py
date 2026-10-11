import sys

from src.domain_onboarding import DomainRequest, client_from_environment, onboard_customer_domain


if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else "example.com"
    result = onboard_customer_domain(client_from_environment(), DomainRequest(
        domain=domain,
        webhook_url="https://your-product.example/hooks/infrai",
        webhook_secret="set-this-in-your-secret-store",
    ))
    print(result)
