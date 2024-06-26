import * as cdk from "aws-cdk-lib";
import * as fs from "fs";
import * as yaml from "js-yaml";

export type Config = {
    readonly env?: cdk.Environment;
    readonly stackName: string;
    readonly logLevel?: string;

    readonly domainName?: string;
    readonly certificateArn?: string;

    readonly slackSigningSecret: string;
    readonly slackBotToken: string;
    readonly slackBotMemberId: string;

    readonly chatGpt: {
        readonly apiKey: string;
        readonly model: string;
        readonly stream?: boolean;
    };
}

/**
 * Create config.
 *
 * @param env Environment name
 */
export function createConfig(env?: string): Config {
    return yaml.load(fs.readFileSync(`config${env ? `.${env}` : ''}.yaml`, 'utf-8')) as Config;
}
