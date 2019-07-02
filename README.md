# NetKAN-Infra
NetKAN Infrastructure Repo


Performing Updates
------------------

**Updating the Stacke:**
```bash
aws cloudformation update-stack --stack-name DevQueues --template-body "`python dev-stack.py`" --capabilities CAPABILITY_IAM --profile ckan --region us-west-2
```
