#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import {SlackChatbotChatgptStack} from "../lib/slack-chatbot-chatgpt-stack";
import {createConfig} from "../lib/config";

const app = new cdk.App();
const config = createConfig(app.node.tryGetContext("env") || process.env.ENV);

new SlackChatbotChatgptStack(app, "SlackChatbotChatgptStack", {
    env: config.env,
    stackName: config.stackName,
    config,
});
