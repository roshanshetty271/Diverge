"""Create a console-visible Bedrock Agent with Action Group pointing to Diverge Lambda.

This script creates an actual "Agent for Amazon Bedrock" resource visible in the AWS console.
It points to the existing Diverge Lambda as an Action Group, so the Bedrock Agent can
orchestrate debates via the console's built-in test UI.

Prerequisites:
  - Bedrock model access approved (us.amazon.nova-pro-v1:0)
  - SAM stack deployed (diverge Lambda function exists)
  - Appropriate IAM permissions

Usage:
  cd backend
  python scripts/setup_bedrock_agent.py

Environment variables:
  AWS_REGION                  — region (default: us-east-1)
  DIVERGE_LAMBDA_ARN          — ARN of the RestApiFunction Lambda
  DIVERGE_KB_ID               — (optional) Knowledge Base ID to associate
  DIVERGE_AGENT_ROLE_ARN      — IAM role ARN for the Bedrock Agent
"""

import os
import json
import time
import boto3


REGION = os.environ.get("AWS_REGION", "us-east-1")
LAMBDA_ARN = os.environ.get("DIVERGE_LAMBDA_ARN", "")
KB_ID = os.environ.get("DIVERGE_KB_ID", "")
AGENT_ROLE_ARN = os.environ.get("DIVERGE_AGENT_ROLE_ARN", "")
ACCOUNT_ID = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

AGENT_NAME = "diverge-decision-engine"
FOUNDATION_MODEL = "us.amazon.nova-pro-v1:0"

AGENT_INSTRUCTION = """You are Diverge, a decision intelligence engine that helps people think through major life decisions.

When a user describes a life decision with two paths (e.g., "Should I take the new job in NYC or stay in my current role?"), you should:

1. Identify the two paths clearly
2. Call the run_debate action with path_a (first option) and path_b (second option)
3. Present the structured debate result to the user, including each round's arguments and the final verdict

You specialize in career changes, startup decisions, education choices, relationship decisions, financial planning, and health-related decisions.

Always be empathetic, balanced, and thorough. Never give simplistic yes/no answers."""

ACTION_GROUP_SCHEMA = {
    "openapi": "3.0.0",
    "info": {
        "title": "Diverge Decision Engine API",
        "version": "1.0.0",
        "description": "API for running structured debates on life decisions",
    },
    "paths": {
        "/debate": {
            "post": {
                "operationId": "runDebate",
                "summary": "Run a structured 5-round debate between two life paths",
                "description": "Executes a multi-round debate where AI agents argue for each path, then delivers a verdict with actionable insights.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["path_a", "path_b"],
                                "properties": {
                                    "path_a": {
                                        "type": "string",
                                        "description": "The first life path option (e.g., 'Take the new job in NYC')",
                                    },
                                    "path_b": {
                                        "type": "string",
                                        "description": "The second life path option (e.g., 'Stay in current role in Boston')",
                                    },
                                    "constraints": {
                                        "type": "string",
                                        "description": "Any constraints or context (e.g., 'I have $50k savings, partner works remotely')",
                                    },
                                    "financial_context": {
                                        "type": "string",
                                        "description": "Financial context (e.g., '$120k salary, $2k/month rent')",
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Debate completed successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "debate_id": {"type": "string"},
                                        "verdict": {"type": "string"},
                                        "completed_rounds": {"type": "integer"},
                                        "total_rounds": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    },
}


def create_agent():
    client = boto3.client("bedrock-agent", region_name=REGION)

    if not AGENT_ROLE_ARN:
        print("ERROR: Set DIVERGE_AGENT_ROLE_ARN to the IAM role for the Bedrock Agent.")
        print("  The role needs: bedrock:InvokeModel, lambda:InvokeFunction, bedrock:Retrieve")
        return None

    print(f"Creating Bedrock Agent: {AGENT_NAME}")
    print(f"  Model: {FOUNDATION_MODEL}")
    print(f"  Region: {REGION}")

    try:
        response = client.create_agent(
            agentName=AGENT_NAME,
            foundationModel=FOUNDATION_MODEL,
            instruction=AGENT_INSTRUCTION,
            agentResourceRoleArn=AGENT_ROLE_ARN,
            idleSessionTTLInSeconds=600,
            description="Decision intelligence engine — runs structured debates on life choices using multi-agent AI. Team Sic Mundus.",
        )
        agent_id = response["agent"]["agentId"]
        print(f"  Agent created: {agent_id}")
        return agent_id

    except client.exceptions.ConflictException:
        print(f"  Agent '{AGENT_NAME}' already exists. Looking up ID...")
        agents = client.list_agents()["agentSummaries"]
        for a in agents:
            if a["agentName"] == AGENT_NAME:
                print(f"  Found existing agent: {a['agentId']}")
                return a["agentId"]
        return None


def add_action_group(client, agent_id):
    if not LAMBDA_ARN:
        print("WARNING: DIVERGE_LAMBDA_ARN not set — skipping Action Group creation.")
        print("  Set it to the ARN of your deployed RestApiFunction Lambda.")
        return

    print(f"Creating Action Group for agent {agent_id}...")

    try:
        response = client.create_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupName="diverge-debate-action",
            actionGroupExecutor={"lambda": LAMBDA_ARN},
            apiSchema={"payload": json.dumps(ACTION_GROUP_SCHEMA)},
            description="Runs a structured debate via the Diverge Lambda orchestrator",
        )
        ag_id = response["agentActionGroup"]["actionGroupId"]
        print(f"  Action Group created: {ag_id}")
    except client.exceptions.ConflictException:
        print("  Action Group already exists — skipping.")


def associate_knowledge_base(client, agent_id):
    if not KB_ID:
        print("INFO: DIVERGE_KB_ID not set — skipping Knowledge Base association.")
        return

    print(f"Associating Knowledge Base {KB_ID} with agent {agent_id}...")

    try:
        client.associate_agent_knowledge_base(
            agentId=agent_id,
            agentVersion="DRAFT",
            knowledgeBaseId=KB_ID,
            description="Relationship psychology, career, and decision-making research for debate enrichment",
        )
        print("  Knowledge Base associated.")
    except client.exceptions.ConflictException:
        print("  Knowledge Base already associated — skipping.")


def prepare_agent(client, agent_id):
    print(f"Preparing agent {agent_id} (this makes it testable in the console)...")
    client.prepare_agent(agentId=agent_id)

    for _ in range(30):
        time.sleep(5)
        resp = client.get_agent(agentId=agent_id)
        status = resp["agent"]["agentStatus"]
        print(f"  Status: {status}")
        if status == "PREPARED":
            return True
        if status == "FAILED":
            print(f"  ERROR: {resp['agent'].get('failureReasons', 'Unknown')}")
            return False
    print("  TIMEOUT: Agent did not reach PREPARED status in 150 seconds.")
    return False


def main():
    print("=" * 60)
    print("Diverge — Bedrock Agent Setup")
    print("=" * 60)

    agent_id = create_agent()
    if not agent_id:
        return

    client = boto3.client("bedrock-agent", region_name=REGION)

    add_action_group(client, agent_id)
    associate_knowledge_base(client, agent_id)

    if prepare_agent(client, agent_id):
        print("\nAgent is ready!")
        print(f"  Console URL: https://{REGION}.console.aws.amazon.com/bedrock/home?region={REGION}#/agents/{agent_id}")
        print("  You can test it in the console's built-in playground.")
    else:
        print("\nAgent creation completed but may need manual preparation in the console.")
        print(f"  Console URL: https://{REGION}.console.aws.amazon.com/bedrock/home?region={REGION}#/agents/{agent_id}")


if __name__ == "__main__":
    main()
