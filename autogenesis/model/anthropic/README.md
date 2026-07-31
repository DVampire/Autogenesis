---
name: model_anthropic
description: "Adapts Anthropic chat requests and responses to Autogenesis's provider-neutral Message and Model contracts. `serializer.py` owns wire conversion; `chat.py` owns the provider client."
version: 1.0.0
type: provider
category: model
requirements: []
metadata: {}
---
# Anthropic model provider

Adapts Anthropic chat requests and responses to Autogenesis's provider-neutral Message and
Model contracts. `serializer.py` owns wire conversion; `chat.py` owns the provider client.
