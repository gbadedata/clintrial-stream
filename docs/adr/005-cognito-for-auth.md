# ADR-005: Cognito for OAuth2/JWT authentication

**Status:** Accepted

## Context

The API must authenticate users (clinical research associates, data managers, investigators) and authorise their actions based on role. The standard for modern HTTP APIs is OAuth2 with JWT bearer tokens. The question is which identity provider issues those tokens.

## Decision

Use **Amazon Cognito User Pools** as the identity provider, with the API verifying JWTs locally via Cognito's published JWKS.

## Alternatives considered

**Auth0 / Okta**

- Excellent developer experience, broad federation support out of the box
- Per-user pricing scales with the user base - fine for a portfolio, less attractive at enterprise scale
- Vendor lock-in to a non-AWS provider creates a billing and compliance touchpoint outside the AWS account boundary

**Keycloak (self-hosted)**

- Open-source, no per-user licensing cost
- Self-hosting means we own patching, backups, HA - operational overhead the platform was explicitly designed to avoid
- Worth the cost for a multi-realm enterprise deployment, overkill here

**Roll our own with Flask sessions**

- Cheapest to write, most expensive to maintain
- Auth is an "easy to do badly" problem - security gotchas around token rotation, password storage, MFA, account recovery accumulate quickly
- Consistently the wrong call for any real system

**API Gateway with IAM authentication**

- AWS-native, no JWT verification logic needed in the app
- Couples the API tightly to AWS identity, which makes external partner access (a common biotech requirement) awkward

## Consequences

**Positive**

- User pool, password policy, MFA, account recovery flows all managed by AWS
- JWT verification is library-level work in the API - `python-jose` validates the token signature against Cognito's JWKS, no callback to Cognito per request
- SAML and OIDC federation supported, so external partners (CROs, sponsors) can be added without rebuilding the auth layer

**Negative**

- Cognito's documentation and console UI are notoriously rough - onboarding cost
- Customising emails, password policies, and tokens is finicky compared to Auth0
- Cognito is region-locked, so multi-region deployments need user pool replication strategies
