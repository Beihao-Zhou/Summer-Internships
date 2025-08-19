import json
import sys
import uuid
from datetime import datetime
import util
import re


def add_https_to_url(url):
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def getData(body, is_edit, username):
    lines = [text.strip("# ") for text in re.split('[\n\r]+', body)]
    
    data = {"date_updated": int(datetime.now().timestamp())}
    
    # Parse all fields using content-based approach
    for i, line in enumerate(lines):
        # URL/Link
        if "Link to Internship Posting" in line:
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["url"] = add_https_to_url(lines[i + 1].strip())
        
        # Company Name
        elif "Company Name" in line:
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["company_name"] = lines[i + 1]
        
        # Title
        elif "Internship Title" in line:
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["title"] = lines[i + 1]
        
        # Location
        elif "Location" in line and "Email" not in line:  # Avoid matching "Email location"
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["locations"] = [loc.strip() for loc in lines[i + 1].split("|")]
        
        # Terms
        elif "What term(s) is this internship offered for?" in line:
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["terms"] = [term.strip() for term in lines[i + 1].split(",")]
        
        # Sponsorship
        elif "Does this internship offer sponsorship?" in line:
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["sponsorship"] = "Other"
                for option in ["Offers Sponsorship", "Does Not Offer Sponsorship", "U.S. Citizenship is Required"]:
                    if option in lines[i + 1]:
                        data["sponsorship"] = option
        
        # Active status
        elif (is_edit and "Is this internship still accepting applications?" in line) or \
             (not is_edit and "Is this internship currently accepting applications?" in line):
            if i + 1 < len(lines) and "none" not in lines[i + 1].lower():
                data["active"] = "yes" in lines[i + 1].lower()
    
    # Handle category selection and advanced degree requirements
    # Use a more robust approach to find the right lines by content
    
    # Find category line
    for i, line in enumerate(lines):
        if "What category does this internship belong to?" in line or "category" in line.lower():
            if i + 1 < len(lines) and "no response" not in lines[i + 1].lower():
                data["category"] = lines[i + 1]
            break
    
    # Find advanced degree requirements
    advanced_degree_checked = False
    for i, line in enumerate(lines):
        if "Advanced Degree Requirements" in line:
            # Look for checkbox in next few lines
            for j in range(i + 1, min(i + 4, len(lines))):
                if j < len(lines) and "[x]" in lines[j].lower():
                    advanced_degree_checked = True
                    break
            break
    
    data["degrees"] = ["Master's"] if advanced_degree_checked else ["Bachelor's"]
    
    # Find email (look for the line after "Email associated with your GitHub account")
    email = "_no response_"
    for i, line in enumerate(lines):
        if "Email associated with your GitHub account" in line:
            if i + 1 < len(lines):
                email = lines[i + 1]
            break
    
    if is_edit:
        # Find the remove checkbox
        for i, line in enumerate(lines):
            if "Permanently remove this internship from the list?" in line:
                if i + 1 < len(lines):
                    data["is_visible"] = "[x]" not in lines[i + 1].lower()
                break
    if "no response" not in email:
        util.setOutput("commit_email", email)
        util.setOutput("commit_username", username)
    else:
        util.setOutput("commit_email", "action@github.com")
        util.setOutput("commit_username", "GitHub Action")
    
    return data


def main():
    event_file_path = sys.argv[1]

    with open(event_file_path) as f:
        event_data = json.load(f)


    # CHECK IF NEW OR OLD INTERNSHIP

    new_internship = "new_internship" in [label["name"] for label in event_data["issue"]["labels"]]
    edit_internship = "edit_internship" in [label["name"] for label in event_data["issue"]["labels"]]

    if not new_internship and not edit_internship:
        util.fail("Only new_internship and edit_internship issues can be approved")


    # GET DATA FROM ISSUE FORM

    issue_body = event_data['issue']['body']
    issue_user = event_data['issue']['user']['login']

    data = getData(issue_body, is_edit=edit_internship, username=issue_user)

    if new_internship:
        data["source"] = issue_user
        data["id"] = str(uuid.uuid4())
        data["date_posted"] = int(datetime.now().timestamp())
        data["company_url"] = ""
        data["is_visible"] = True

    # remove utm-source
    utm = data["url"].find("?utm_source")
    if utm == -1:
        utm = data["url"].find("&utm_source")
    if utm != -1:
        data["url"] = data["url"][:utm]


    # UPDATE LISTINGS

    def get_commit_text(listing):
        closed_text = "" if listing["active"] else "(Closed)"
        sponsorship_text = "" if listing["sponsorship"] == "Other" else ("(" + listing["sponsorship"] + ")")
        listing_text = (listing["title"].strip() + " at " + listing["company_name"].strip() + " " + closed_text + " " + sponsorship_text).strip()
        return listing_text

    with open(".github/scripts/listings.json", "r") as f:
        listings = json.load(f)

    if listing_to_update := next(
        (item for item in listings if item["url"] == data["url"]), None
    ):
        if new_internship:
            util.fail("This internship is already in our list. See CONTRIBUTING.md for how to edit a listing")
        for key, value in data.items():
            listing_to_update[key] = value

        util.setOutput("commit_message", "updated listing: " + get_commit_text(listing_to_update))
    else:
        if edit_internship:
            util.fail("We could not find this internship in our list. Please double check you inserted the right url")
        listings.append(data)

        util.setOutput("commit_message", "added listing: " + get_commit_text(data))

    with open(".github/scripts/listings.json", "w") as f:
        f.write(json.dumps(listings, indent=4))


if __name__ == "__main__":
    main()
