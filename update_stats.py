import os
import urllib.request
import urllib.error
import json
import re
import sys

def make_request(url, headers, data=None, retries=3):
    import time
    if data:
        data = json.dumps(data).encode('utf-8')
    
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                if response.status == 202:
                    # 202 Accepted means GitHub is computing stats in background
                    time.sleep(2)
                    continue
                body = response.read().decode('utf-8')
                if not body:
                    return None
                return json.loads(body)
        except urllib.error.URLError as e:
            if hasattr(e, 'code') and e.code == 202:
                time.sleep(2)
                continue
            print(f"Request failed for {url}: {e}")
            return None
    
    return None

def fetch_github_stats(token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Stats-Updater"
    }
    
    username_data = make_request('https://api.github.com/user', headers)
    if not username_data or 'login' not in username_data:
        print(f"Failed to fetch user data. Check if your token is valid and has 'read:user' scope. Response: {username_data}")
        return None
    
    user_query = {"query": "query { viewer { id } }"}
    user_data = make_request('https://api.github.com/graphql', headers, user_query)
    user_id = user_data['data']['viewer']['id']
    
    repo_query = """
    query {
      viewer {
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          nodes {
            name
            stargazerCount
            defaultBranchRef {
              target {
                ... on Commit {
                  history(author: {id: "%s"}) {
                    totalCount
                  }
                }
              }
            }
          }
        }
        followers {
          totalCount
        }
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) {
          totalCount
        }
      }
    }
    """
    
    graphql_req = {"query": repo_query % user_id}
    data_res = make_request('https://api.github.com/graphql', headers, graphql_req)
    if not data_res or 'errors' in data_res:
        print(f"Failed to fetch GraphQL data: {data_res.get('errors') if data_res else 'Network/Auth Error'}")
        return None
        
    data = data_res['data']['viewer']
    
    repos = data['repositories']['nodes']
    total_repos = len(repos)
    total_stars = sum(repo.get('stargazerCount', 0) for repo in repos)
    
    total_commits = 0
    for repo in repos:
        if repo.get('defaultBranchRef') and repo['defaultBranchRef'].get('target'):
            total_commits += repo['defaultBranchRef']['target']['history']['totalCount']
            
    total_contributed = data['repositoriesContributedTo']['totalCount']
    total_followers = data['followers']['totalCount']
    username = username_data['login']
    
    loc_add = 0
    loc_del = 0

    for repo in repos:
        repo_name = repo['name']
        stats_url = f"https://api.github.com/repos/{username}/{repo_name}/stats/contributors"
        contributors = make_request(stats_url, headers)
        
        if isinstance(contributors, list):
            for contributor in contributors:
                if contributor.get('author') and contributor['author'].get('login', '').lower() == username.lower():
                    for week in contributor.get('weeks', []):
                        loc_add += week.get('a', 0)
                        loc_del += week.get('d', 0)
                        
    loc_total = loc_add - loc_del
    
    return {
        'repo_data': str(total_repos),
        'contrib_data': str(total_contributed),
        'star_data': str(total_stars),
        'commit_data': f"{total_commits:,}",
        'follower_data': str(total_followers),
        'loc_data': f"{loc_total:,}",
        'loc_add': f"{loc_add:,}",
        'loc_del': f"{loc_del:,}"
    }

def update_svg(filename, stats):
    if not os.path.exists(filename):
        print(f"File {filename} not found.")
        return
        
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    for key, value in stats.items():
        pattern = rf'(id="{key}">)(.*?)(</tspan>)'
        replacement = rf'\g<1>{value}\g<3>'
        content = re.sub(pattern, replacement, content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated {filename}")

if __name__ == "__main__":
    token = os.environ.get('GH_TOKEN')
    if not token:
        print("ERROR: GH_TOKEN environment variable is not set!")
        print("To run this locally, use: $env:GH_TOKEN=\"your_token\"; python update_stats.py")
        print("Or run it via GitHub Actions where the secret is configured.")
        sys.exit(1)
        
    stats = fetch_github_stats(token)
    if not stats:
        sys.exit(1)
            
    update_svg('darkmode.svg', stats)
    update_svg('lightmode.svg', stats)
