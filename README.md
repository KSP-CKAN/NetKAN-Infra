# NetKAN-Infra
The NetKAN Infrastructure Project is a re-write of the original monolithic NetKAN-bot, with the goal of easier maintenance, a faster code to deployment pipeline, infrastructure as code.


Performing Updates
------------------

**Updating the Stack:**
```bash
aws cloudformation update-stack --stack-name DevQueues --template-body "`python dev-stack.py`" --capabilities CAPABILITY_IAM --profile ckan --region us-west-2
```
