
def check(state):
    if (('agegate', 'response')) in state:
        return state['agegate', 'response'] == "Yes"
    response = None
    while response not in ("Yes", "No"):
        response = input("This feed contains content marked as mature (18+). Are you at least 18 years of age, legally allowed to see such content in your jurisdiction, and do you wish to see this content(Yes/No)? ")
    state['agegate', 'response'] = response
    return response == 'Yes'

