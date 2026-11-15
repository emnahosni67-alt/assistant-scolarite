import uuid
from langchain_core.messages import HumanMessage
from agent.graph import app

if __name__ == "__main__":
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    print("Assistant ISET Charguia prêt (tapez 'quit' pour quitter).\n")
    
    while True:
        q = input("Vous : ")
        if q.strip().lower() in ("quit", "exit"):
            break
        res = app.invoke({"messages": [HumanMessage(content=q)]}, config=config)
        print("Agent :", res["messages"][-1].content, "\n")